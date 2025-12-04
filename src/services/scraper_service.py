import httpx
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Set, Tuple, List

# --- CONSTANTES DE CONTROL REVISADAS ---
MAX_PAGES_TO_CRAWL = 5  
MAX_CONTEXT_LENGTH = 100000 
TIMEOUT_SECONDS = 3.0 # Tiempo de espera máximo por cada página.

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MicroserviceBot/1.0)",
    "Accept": "text/html"
}

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

async def _fetch_and_scrape(client: httpx.AsyncClient, url: str) -> Tuple[str, str]:
    """Función auxiliar para descargar y raspar una URL individual con mejor manejo de errores."""
    print(f"DEBUG: Intentando descargar URL: {url}")
    try:
        # Usamos response.content y forzamos decodificación a UTF-8 (más robusto)
        response = await client.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        response.raise_for_status() 

        # Decodificar el contenido binario a texto (forzando UTF-8 si es necesario)
        try:
            html_content = response.content.decode('utf-8')
        except UnicodeDecodeError:
            print(f"ADVERTENCIA: Falló decodificación UTF-8 para {url}. Intentando ISO-8859-1.")
            html_content = response.content.decode('iso-8859-1', errors='ignore')

        clean_text = _clean_and_extract_text(html_content)
        
        print(f"DEBUG: Descarga exitosa. Longitud de texto extraído: {len(clean_text)} caracteres.")
        return url, clean_text

    except httpx.RequestError as e:
        print(f"ADVERTENCIA: Falló la descarga de {url} (Timeout o Red). Error: {e}")
        return url, ""
    except httpx.HTTPStatusError as e:
        print(f"ADVERTENCIA: Error HTTP {e.response.status_code} en {url}. Saltando página.")
        return url, ""

async def scrape_url_with_context(url: str) -> str:
    """
    Rastrea la URL principal, extrae N enlaces internos y raspa su contenido
    de forma paralela para construir un contexto masivo para Gemini.
    """
    async with httpx.AsyncClient() as client:
        # 1. Scraping de la página principal
        main_url, main_text = await _fetch_and_scrape(client, url)
        
        if not main_text:
            raise Exception("La página principal no pudo ser accedida o no tiene contenido.")

        # 2. Extracción de enlaces y scraping paralelo de secundarios
        # Usamos el texto de la página principal para obtener los enlaces
        main_soup = BeautifulSoup(main_text, "html.parser")
        potential_links = _get_internal_links(main_soup, url)
        
        secondary_links: List[str] = [
            link for link in potential_links 
            if link != main_url.rstrip('/')
        ][:MAX_PAGES_TO_CRAWL]
        
        print(f"DEBUG: Enlaces secundarios a rastrear: {len(secondary_links)}")

        tasks = [_fetch_and_scrape(client, link) for link in secondary_links]
        results: List[Tuple[str, str]] = await asyncio.gather(*tasks)

        # 3. Concatenación y límite de contexto
        full_context = [f"--- CONTEXTO PRINCIPAL: {main_url} ---\n{main_text}"]
        current_length = len(main_text)
        
        for link, text in results:
            if text and current_length + len(text) < MAX_CONTEXT_LENGTH:
                full_context.append(f"\n--- CONTEXTO ADICIONAL: {link} ---\n{text}")
                current_length += len(text)
            elif text:
                print(f"DEBUG: Contexto omitido de {link} - Límite de {MAX_CONTEXT_LENGTH} caracteres alcanzado.")
                break 
        
        final_context = "".join(full_context)
        print(f"DEBUG FINAL: Longitud total del contexto enviado a Gemini: {len(final_context)} caracteres.")
        
        return final_context