import httpx
from bs4 import BeautifulSoup

async def scrape_url(url: str) -> str:
    """
    Descarga el HTML de la URL y extrae el texto visible limpio.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; MicroserviceBot/1.0)"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise Exception(f"Error al acceder a la URL: {str(e)}")

    soup = BeautifulSoup(response.text, "html.parser")

    # Eliminar elementos no deseados (scripts, estilos, metadata)
    for script_or_style in soup(["script", "style", "header", "footer", "nav"]):
        script_or_style.decompose()

    # Obtener texto y limpiar espacios en blanco
    text = soup.get_text(separator=" ")
    clean_text = " ".join(text.split())

    # Limitamos el texto preventivamente (ej. 20000 caracteres) para no saturar si es muy largo
    return clean_text[:20000]