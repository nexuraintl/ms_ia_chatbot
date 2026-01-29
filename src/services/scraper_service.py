import httpx
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Set, Tuple, List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pydantic import HttpUrl

# --- CONSTANTES DE CONTROL REVISADAS ---
MAX_PAGES_TO_CRAWL = 5  
MAX_CONTEXT_LENGTH = 100000 
TIMEOUT_SECONDS = 5.0 # Tiempo de espera máximo por cada página.

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

# src/services/scraper_service.py

# --- CONSTANTES DE CONTROL REVISADAS ---
MAX_PAGES_TO_CRAWL = 5  
MAX_CONTEXT_LENGTH = 100000 
TIMEOUT_SECONDS = 5.0 # <-- AUMENTAMOS ligeramente, confiando en tenacity para reintentos.

# ... (otras funciones auxiliares y decorador @retry siguen iguales)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS)
)
async def _fetch_and_scrape(client: httpx.AsyncClient, url: str) -> Tuple[str, str]:
    """Función auxiliar que descarga y retorna el HTML crudo con manejo de redirecciones."""
    print(f"DEBUG: Intentando descargar URL: {url}")
    try:
        # Añadimos follow_redirects=True para manejar 301/302 automáticamente.
        response = await client.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True)
        
        # raise_for_status solo se llama si el código es 4xx o 5xx.
        response.raise_for_status() 

        # ... (Decodificación del contenido sigue igual)
        try:
            html_content = response.content.decode('utf-8')
        except UnicodeDecodeError:
            print(f"ADVERTENCIA: Falló decodificación UTF-8 para {url}. Intentando ISO-8859-1.")
            html_content = response.content.decode('iso-8859-1', errors='ignore')

        return url, html_content

    except httpx.RequestError as e:
        # Error de red/timeout -> Dispara el reintento de Tenacity
        print(f"ADVERTENCIA: Falló la descarga de {url} (Reintentando...). Error: {type(e).__name__}")
        raise e 
    except httpx.HTTPStatusError as e:
        # No reintentamos errores 4xx/5xx definitivos.
        print(f"ADVERTENCIA: Error HTTP {e.response.status_code} en {url}. Saltando página.")
        return url, ""
    
# src/services/scraper_service.py

# Importamos la función de filtrado (asegúrate de tenerla en gemini_service.py)
from src.services.gemini_service import filter_relevant_links 

async def scrape_url_with_context(url: str, question: str) -> str:
    """
    Rastrea la URL principal y utiliza IA para elegir qué enlaces 
    secundarios son relevantes para la pregunta antes de rasparlos.
    """
    async with httpx.AsyncClient() as client:
        # 1. Scraping de la página principal (HTML crudo)
        main_url, raw_html = await _fetch_and_scrape(client, url)
        
        if not raw_html:
            raise Exception("La página principal no pudo ser accedida o no tiene contenido.")

        # 2. Extracción de enlaces (Obtenemos Tuplas de: título, url)
        main_soup = BeautifulSoup(raw_html, "html.parser")
        # Nota: Asegúrate que tu función _get_internal_links devuelva List[Tuple[str, str]]
        potential_links = _get_internal_links(main_soup, url)
        
        # 3. Limpieza del texto de la página principal
        main_text = _clean_and_extract_text(raw_html)

        # 4. 🔥 FILTRADO INTELIGENTE (Aquí usamos la 'question')
        print(f"DEBUG: Enviando {len(potential_links)} enlaces a Gemini para filtrar por relevancia...")
        
        # Llamamos a Gemini para que nos diga cuáles de esos 116 enlaces sirven para la pregunta
        relevant_urls = await filter_relevant_links(question, potential_links, MAX_PAGES_TO_CRAWL)
        
        # Filtramos para no repetir la URL principal si aparecía en los links
        secondary_links = [l for l in relevant_urls if l != main_url.rstrip('/')]

        print(f"DEBUG: Enlaces seleccionados por IA: {secondary_links}")

        # 5. Scraping Paralelo de las URLs seleccionadas
        tasks = [_fetch_and_scrape(client, link) for link in secondary_links]
        results = await asyncio.gather(*tasks)

        # 6. Concatenación de resultados
        full_context = [f"--- CONTEXTO PRINCIPAL: {main_url} ---\n{main_text}"]
        current_length = len(main_text)

        for link, raw_content in results:
            if raw_content:
                secondary_text = _clean_and_extract_text(raw_content) 
                if current_length + len(secondary_text) < MAX_CONTEXT_LENGTH:
                    full_context.append(f"\n--- CONTEXTO ADICIONAL RELEVANTE: {link} ---\n{secondary_text}")
                    current_length += len(secondary_text)
                else:
                    break 

        final_context = "".join(full_context)
        print(f"DEBUG FINAL: Contexto total optimizado: {len(final_context)} caracteres.")
        
        return final_context

async def scrape_specific_urls(urls: List[HttpUrl]) -> str:
    """
    Descarga y limpia el contenido de una lista específica de URLs en paralelo.
    """
    async with httpx.AsyncClient() as client:
        # Creamos las tareas de descarga para cada URL recibida
        tasks = [_fetch_and_scrape(client, str(u)) for u in urls]
        results = await asyncio.gather(*tasks)

        full_context = []
        current_length = 0

        for url, raw_html in results:
            if raw_html:
                text = _clean_and_extract_text(raw_html)
                if current_length + len(text) < MAX_CONTEXT_LENGTH:
                    full_context.append(f"\n--- CONTENIDO DE: {url} ---\n{text}")
                    current_length += len(text)
                else:
                    break

        return "".join(full_context)