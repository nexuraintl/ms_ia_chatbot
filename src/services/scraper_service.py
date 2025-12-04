import httpx
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Set, Tuple, List

# --- CONSTANTES DE CONTROL ---
MAX_PAGES_TO_CRAWL = 5  # Limita el número de páginas secundarias a rastrear.
MAX_CONTEXT_LENGTH = 100000 # Limita el total de caracteres de contexto.
TIMEOUT_SECONDS = 5.0 # Tiempo de espera por cada solicitud HTTP.

# Configuración de encabezados para simular un navegador
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MicroserviceBot/1.0)",
    "Accept": "text/html"
}

def _clean_and_extract_text(html_content: str) -> str:
    """Extrae texto limpio de un fragmento HTML, eliminando scripts, estilos, etc."""
    soup = BeautifulSoup(html_content, "html.parser")

    # Eliminar elementos no deseados (scripts, estilos, navegación, pies de página)
    for element in soup(["script", "style", "header", "footer", "nav", "form"]):
        element.decompose()

    # Obtener texto y limpiar espacios en blanco
    text = soup.get_text(separator=" ")
    return " ".join(text.split())

def _get_internal_links(soup: BeautifulSoup, base_url: str) -> Set[str]:
    """Extrae enlaces internos únicos de la página base."""
    base_netloc = urlparse(base_url).netloc
    internal_links = set()
    
    for link_tag in soup.find_all('a', href=True):
        href = link_tag['href']
        
        # Resuelve rutas relativas (ej. /contacto) a rutas absolutas
        full_url = urljoin(base_url, href)
        parsed_url = urlparse(full_url)
        
        # Filtra: Debe ser HTTP/HTTPS, debe ser del mismo dominio (base_netloc)
        # y no debe ser un simple enlace de ancla (#section)
        if (parsed_url.scheme in ('http', 'https') and
            parsed_url.netloc == base_netloc and
            parsed_url.fragment == ''):
            
            # Reconstruye la URL sin parámetros (limpieza simple)
            clean_url = parsed_url.scheme + "://" + parsed_url.netloc + parsed_url.path
            internal_links.add(clean_url)
            
    return internal_links

async def _fetch_and_scrape(client: httpx.AsyncClient, url: str) -> Tuple[str, str]:
    """Función auxiliar para descargar y raspar una URL individual."""
    try:
        response = await client.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
        response.raise_for_status() # Lanza HTTPStatusError si es 4xx/5xx
        
        # Limpieza y extracción de texto
        clean_text = _clean_and_extract_text(response.text)
        
        # Devolvemos la URL y el texto
        return url, clean_text

    except httpx.RequestError as e:
        # Errores de red o timeout
        print(f"Advertencia: Falló la descarga de {url}. Error: {e}")
        return url, ""
    except httpx.HTTPStatusError as e:
        # Errores de estado HTTP (404, 500, etc.)
        print(f"Advertencia: Error HTTP {e.response.status_code} en {url}.")
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

        # 2. Extracción de enlaces de la página principal
        main_soup = BeautifulSoup(main_text, "html.parser")
        potential_links = _get_internal_links(main_soup, url)
        
        # 3. Selección y filtrado de enlaces secundarios (evitamos auto-rastreo)
        secondary_links: List[str] = [
            link for link in potential_links 
            if link != main_url.rstrip('/')
        ][:MAX_PAGES_TO_CRAWL]
        
        print(f"Rastreando {len(secondary_links)} enlaces secundarios de forma paralela.")

        # 4. Scraping paralelo de las páginas secundarias
        # Creamos una lista de tareas (futures) para ejecución asíncrona
        tasks = [_fetch_and_scrape(client, link) for link in secondary_links]
        
        # Ejecutamos todas las tareas en paralelo (esperamos a que todas terminen)
        results: List[Tuple[str, str]] = await asyncio.gather(*tasks)

        # 5. Concatenación y límite de contexto
        full_context = [f"--- INICIO CONTEXTO: {main_url} ---\n{main_text}"]
        current_length = len(main_text)
        
        for link, text in results:
            if text and current_length + len(text) < MAX_CONTEXT_LENGTH:
                # Agregamos solo si no excedemos el límite global
                full_context.append(f"\n--- CONTEXTO ADICIONAL: {link} ---\n{text}")
                current_length += len(text)
            elif text:
                print(f"Contexto omitido de {link} para no exceder el límite de {MAX_CONTEXT_LENGTH} caracteres.")
                break # Si se excede el límite, detenemos la adición de más contexto
        
        return "".join(full_context)