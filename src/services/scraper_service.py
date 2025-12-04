import httpx
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Set, Tuple, List

# --- CONSTANTES DE CONTROL REVISADAS ---
MAX_PAGES_TO_CRAWL = 5  
MAX_CONTEXT_LENGTH = 100000 
TIMEOUT_SECONDS = 3.0 # REDUCIDO: 3 segundos por página para reducir latencia total.

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MicroserviceBot/1.0)",
    "Accept": "text/html"
}

# Las funciones _clean_and_extract_text y _get_internal_links quedan sin cambios (por brevedad, asumimos que son las mismas)

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
            # Opción de fallback si UTF-8 falla (ej. si es ISO-8859-1)
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
    Rastrea la URL principal y URLs secundarias. (Función principal)
    """
    async with httpx.AsyncClient() as client:
        # 1. Scraping de la página principal
        main_url, main_text = await _fetch_and_scrape(client, url)
        
        if not main_text:
            raise Exception("La página principal no pudo ser accedida o no tiene contenido.")

        # 2. Extracción de enlaces y scraping paralelo de secundarios
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
            # Solo si hay texto y si cabe en el contexto total
            if text and current_length + len(text) < MAX_CONTEXT_LENGTH:
                full_context.append(f"\n--- CONTEXTO ADICIONAL: {link} ---\n{text}")
                current_length += len(text)
            elif text:
                print(f"DEBUG: Contexto omitido de {link} - Límite de {MAX_CONTEXT_LENGTH} caracteres alcanzado.")
                break 
        
        final_context = "".join(full_context)
        print(f"DEBUG FINAL: Longitud total del contexto enviado a Gemini: {len(final_context)} caracteres.")
        
        return final_context