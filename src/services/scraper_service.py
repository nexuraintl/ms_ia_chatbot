import httpx
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Tuple, List, Set
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pydantic import HttpUrl

# Importamos la función de filtrado desde nuestro servicio de IA
from src.services.gemini_service import filter_relevant_links 

# --- CONSTANTES DE CONTROL ---
MAX_PAGES_TO_CRAWL = 5  
MAX_CONTEXT_LENGTH = 100000 
TIMEOUT_SECONDS = 5.0 

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MicroserviceBot/1.0)",
    "Accept": "text/html"
}

RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
)

# --- FUNCIONES AUXILIARES (HELPERS) ---

def _clean_and_extract_text(html_content: str) -> str:
    """Extrae texto limpio de un fragmento HTML, eliminando ruido (scripts, nav, etc.)."""
    soup = BeautifulSoup(html_content, "html.parser")
    for element in soup(["script", "style", "header", "footer", "nav", "form", "aside"]):
        element.decompose()
    text = soup.get_text(separator=" ")
    return " ".join(text.split())

def _get_internal_links(soup: BeautifulSoup, base_url: str) -> List[Tuple[str, str]]:
    """
    Extrae enlaces internos únicos junto con su texto (título).
    Es vital para que la IA pueda decidir qué enlaces son relevantes.
    """
    base_netloc = urlparse(base_url).netloc
    internal_links = []
    seen_urls = set()
    
    for link_tag in soup.find_all('a', href=True):
        href = link_tag['href']
        title = link_tag.get_text(strip=True) # El texto del enlace
        
        if not title: # Ignoramos enlaces sin texto
            continue

        full_url = urljoin(base_url, href)
        parsed_url = urlparse(full_url)
        
        # Filtro: mismo dominio, esquema web y sin anclas (#)
        if (parsed_url.scheme in ('http', 'https') and
            parsed_url.netloc == base_netloc and
            parsed_url.fragment == ''):
            
            clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
            
            if clean_url not in seen_urls:
                internal_links.append((title, clean_url))
                seen_urls.add(clean_url)
            
    print(f"DEBUG LINKS: Se extrajeron {len(internal_links)} enlaces con título para filtrar.")
    return internal_links

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS)
)
async def _fetch_and_scrape(client: httpx.AsyncClient, url: str) -> Tuple[str, str]:
    """Descarga el HTML crudo con soporte para redirecciones y reintentos."""
    print(f"DEBUG: Descargando -> {url}")
    try:
        response = await client.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True)
        response.raise_for_status() 

        try:
            html_content = response.content.decode('utf-8')
        except UnicodeDecodeError:
            html_content = response.content.decode('iso-8859-1', errors='ignore')

        return url, html_content

    except httpx.RequestError as e:
        print(f"ADVERTENCIA: Reintentando {url} debido a error de red: {type(e).__name__}")
        raise e 
    except httpx.HTTPStatusError as e:
        print(f"ADVERTENCIA: Error HTTP {e.response.status_code} en {url}. Saltando.")
        return url, ""

# --- FUNCIONES PRINCIPALES DE NEGOCIO ---

async def scrape_url_with_context(url: str, question: str) -> str:
    """
    MODO EXPLORADOR: Rastrea el mapa del sitio y usa IA para elegir qué páginas leer.
    """
    async with httpx.AsyncClient() as client:
        # 1. Scraping de la página principal
        main_url, raw_html = await _fetch_and_scrape(client, url)
        
        if not raw_html:
            raise Exception("No se pudo acceder a la URL principal.")

        # 2. Extracción de enlaces con títulos
        main_soup = BeautifulSoup(raw_html, "html.parser")
        potential_links = _get_internal_links(main_soup, url)
        main_text = _clean_and_extract_text(raw_html)

        # 3. Filtrado Inteligente con Gemini
        print(f"DEBUG: Consultando a Gemini para filtrar {len(potential_links)} enlaces...")
        relevant_urls = await filter_relevant_links(question, potential_links, MAX_PAGES_TO_CRAWL)
        
        # Evitamos re-descargar la principal
        secondary_links = [l for l in relevant_urls if l.rstrip('/') != main_url.rstrip('/')]
        print(f"DEBUG: IA seleccionó {len(secondary_links)} URLs relevantes.")

        # 4. Rastreo Paralelo de los seleccionados
        tasks = [_fetch_and_scrape(client, link) for link in secondary_links]
        results = await asyncio.gather(*tasks)

        # 5. Construcción del Contexto
        full_context = [f"--- CONTEXTO PRINCIPAL: {main_url} ---\n{main_text}"]
        current_length = len(main_text)

        for link, raw_content in results:
            if raw_content:
                text = _clean_and_extract_text(raw_content) 
                if current_length + len(text) < MAX_CONTEXT_LENGTH:
                    full_context.append(f"\n--- CONTEXTO ADICIONAL RELEVANTE: {link} ---\n{text}")
                    current_length += len(text)
                else:
                    break 

        return "".join(full_context)

async def scrape_specific_urls(urls: List[HttpUrl]) -> str:
    """
    MODO SELECCIÓN DIRECTA: Raspa solo la lista de URLs proporcionada.
    """
    async with httpx.AsyncClient() as client:
        tasks = [_fetch_and_scrape(client, str(u)) for u in urls]
        results = await asyncio.gather(*tasks)

        full_context = []
        current_length = 0

        for url, raw_html in results:
            if raw_html:
                text = _clean_and_extract_text(raw_html)
                if current_length + len(text) < MAX_CONTEXT_LENGTH:
                    full_context.append(f"\n--- CONTENIDO ESPECÍFICO: {url} ---\n{text}")
                    current_length += len(text)
                else:
                    break

        return "".join(full_context)