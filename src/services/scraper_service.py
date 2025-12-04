import httpx
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Set, Tuple, List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# --- CONSTANTES DE CONTROL REVISADAS ---
MAX_PAGES_TO_CRAWL = 5  
MAX_CONTEXT_LENGTH = 100000 
TIMEOUT_SECONDS = 3.0 # Tiempo de espera máximo por cada página.

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MicroserviceBot/1.0)",
    "Accept": "text/html"
}

# Definimos los errores de httpx que queremos reintentar
RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
)

# --- FUNCIONES AUXILIARES FALTANTES ---

def _clean_and_extract_text(html_content: str) -> str:
    """Extrae texto limpio de un fragmento HTML, eliminando scripts, estilos, etc."""
    soup = BeautifulSoup(html_content, "html.parser")

    # Eliminar elementos no deseados (scripts, estilos, navegación, pies de página, formularios)
    for element in soup(["script", "style", "header", "footer", "nav", "form"]):
        element.decompose()

    # Obtener texto y limpiar espacios en blanco
    text = soup.get_text(separator=" ")
    return " ".join(text.split())

def _get_internal_links(soup: BeautifulSoup, base_url: str) -> Set[str]:
    """Extrae enlaces internos únicos de la página base."""
    base_netloc = urlparse(base_url).netloc
    internal_links = set()
    raw_links_found = 0 # <-- NUEVA LÍNEA DE DEBUG

    for link_tag in soup.find_all('a', href=True):
        href = link_tag['href']
        raw_links_found += 1 # <-- NUEVA LÍNEA DE DEBUG

        # Resuelve rutas relativas a rutas absolutas
        full_url = urljoin(base_url, href)
        parsed_url = urlparse(full_url)
        
        # Filtra: Debe ser HTTP/HTTPS, debe ser del mismo dominio (base_netloc)
        if (parsed_url.scheme in ('http', 'https') and
            parsed_url.netloc == base_netloc and
            parsed_url.fragment == ''):
            
            # Reconstruye la URL sin parámetros de query/fragmento (limpieza simple)
            clean_url = parsed_url.scheme + "://" + parsed_url.netloc + parsed_url.path
            internal_links.add(clean_url)
            
    print(f"DEBUG LINKS: BeautifulSoup encontró {raw_links_found} enlaces <a>. {len(internal_links)} pasaron el filtro interno.") # <-- NUEVA LÍNEA DE DEBUG
    return internal_links

# --- FUNCIÓN PRINCIPAL DE RASTREO (Versión Asíncrona con Debugging) ---

@retry(
    stop=stop_after_attempt(3), # Intentar un máximo de 3 veces
    wait=wait_exponential(multiplier=1, min=2, max=10), # Esperar 2s, 4s, etc. entre intentos
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS) # Solo reintentar si es error de red/timeout
)
async def _fetch_and_scrape(client: httpx.AsyncClient, url: str) -> Tuple[str, str]:
    """Función auxiliar que descarga y retorna el HTML crudo con lógica de reintentos."""
    print(f"DEBUG: Intentando descargar URL: {url}")
    try:
        response = await client.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        response.raise_for_status() 

        # ... (Decodificación del contenido sigue igual)
        try:
            html_content = response.content.decode('utf-8')
        except UnicodeDecodeError:
            print(f"ADVERTENCIA: Falló decodificación UTF-8 para {url}. Intentando ISO-8859-1.")
            html_content = response.content.decode('iso-8859-1', errors='ignore')

        return url, html_content

    except httpx.RequestError as e:
        # Relanzamos el error si es un tipo reintentable
        print(f"ADVERTENCIA: Falló la descarga de {url} (Reintentando...). Error: {type(e).__name__}")
        raise e # Esto dispara el reintento por el decorador @retry
    except httpx.HTTPStatusError as e:
        # No reintentamos errores 4xx/5xx (estos son definitivos)
        print(f"ADVERTENCIA: Error HTTP {e.response.status_code} en {url}. Saltando página.")
        return url, ""
    
async def scrape_url_with_context(url: str) -> str:
    """
    Rastrea la URL principal, extrae N enlaces internos y raspa su contenido.
    """
    async with httpx.AsyncClient() as client:
        # 1. Scraping de la página principal (obtenemos HTML crudo)
        main_url, raw_html = await _fetch_and_scrape(client, url) # <-- Ahora es raw_html
        
        if not raw_html:
            raise Exception("La página principal no pudo ser accedida o no tiene contenido.")

        # --- ORDEN CORRECTO DE PROCESAMIENTO ---
        
        # 2. Extracción de enlaces (DEBE USAR EL HTML CRUDO)
        main_soup = BeautifulSoup(raw_html, "html.parser") # <-- Creamos el soup del HTML crudo
        potential_links = _get_internal_links(main_soup, url)
        
        # 3. Limpieza para obtener el contexto de la página principal
        main_text = _clean_and_extract_text(raw_html) # <-- Limpiamos el texto principal
        
        # 4. Filtrado y preparación para el rastreo paralelo
        secondary_links: List[str] = [
            link for link in potential_links 
            if link != main_url.rstrip('/')
        ][:MAX_PAGES_TO_CRAWL]
        
        print(f"DEBUG: Enlaces secundarios a rastrear: {len(secondary_links)}")

        tasks = [_fetch_and_scrape(client, link) for link in secondary_links]
        results: List[Tuple[str, str]] = await asyncio.gather(*tasks)

        # 5. Concatenación y límite de contexto
        # ... (El resto de la función de concatenación sigue igual, solo que ahora los resultados de results son HTML crudo)
        
        full_context = [f"--- CONTEXTO PRINCIPAL: {main_url} ---\n{main_text}"]
        current_length = len(main_text)

        for link, raw_content in results: # <-- raw_content es el HTML crudo
            if raw_content:
                # Limpiamos el texto de las páginas secundarias justo antes de añadirlo
                secondary_text = _clean_and_extract_text(raw_content) 
                
                if current_length + len(secondary_text) < MAX_CONTEXT_LENGTH:
                    full_context.append(f"\n--- CONTEXTO ADICIONAL: {link} ---\n{secondary_text}")
                    current_length += len(secondary_text)
                else:
                    print(f"DEBUG: Contexto omitido de {link} - Límite de {MAX_CONTEXT_LENGTH} caracteres alcanzado.")
                    break 

        final_context = "".join(full_context)
        print(f"DEBUG FINAL: Longitud total del contexto enviado a Gemini: {len(final_context)} caracteres.")
        
        return final_context