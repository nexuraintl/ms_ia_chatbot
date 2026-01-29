import google.generativeai as genai
from src.config import settings
from typing import List, Tuple

# Configuración única
genai.configure(api_key=settings.GEMINI_API_KEY)

# Instanciamos el modelo
model = genai.GenerativeModel('gemini-2.0-flash') # Puedes usar 1.5-flash o 2.0-flash

async def generate_answer(question: str, context_text: str) -> str:
    """
    Genera una respuesta experta basada ÚNICAMENTE en el contexto, 
    sin mostrar URLs ni mencionar las fuentes.
    """
    prompt = f"""
    Actúa como un asistente experto y servicial. Tu objetivo es responder la pregunta del usuario basándote exclusivamente en el contexto proporcionado.

    REGLAS CRÍTICAS:
    1. ÚNICAMENTE usa la información del CONTEXTO para responder.
    2. PROHIBICIÓN TOTAL DE URLs: No incluyas enlaces ni direcciones web.
    3. NO MENCIONES LA FUENTE: Responde de forma directa, sin frases como "según el texto".
    4. Si la información no está en el contexto, indica amigablemente que no tienes esa información específica.

    CONTEXTO:
    {context_text}

    PREGUNTA:
    {question}
    """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error al generar respuesta: {str(e)}"

async def filter_relevant_links(question: str, links: List[Tuple[str, str]], max_links: int = 5) -> List[str]:
    """
    NUEVA FUNCIÓN: Usa IA para seleccionar qué URLs del mapa del sitio 
    son útiles para la pregunta actual.
    """
    if not links:
        return []

    # Formateamos la lista de enlaces para que la IA los entienda
    link_list_str = "\n".join([f"- Título: {title} | URL: {url}" for title, url in links])
    
    prompt = f"""
    Eres un experto en navegación web. Tu tarea es filtrar una lista de enlaces y seleccionar solo los que ayuden a responder la pregunta del usuario.

    PREGUNTA: "{question}"

    LISTA DE ENLACES:
    {link_list_str}

    INSTRUCCIONES:
    1. Selecciona máximo {max_links} URLs que tengan la mayor probabilidad de contener la respuesta.
    2. Responde ÚNICAMENTE con las URLs puras separadas por comas.
    3. Si ningún enlace es relevante, responde con la palabra: NINGUNO.
    """
    
    try:
        response = model.generate_content(prompt)
        content = response.text.strip()
        
        if "NINGUNO" in content:
            return []
            
        # Limpiamos la respuesta para obtener solo las URLs
        urls = [url.strip() for url in content.split(",") if "http" in url]
        return urls[:max_links]
    except Exception as e:
        print(f"DEBUG: Error en filtro de enlaces: {e}")
        # Si falla, devolvemos los primeros para no romper el flujo
        return [url for _, url in links[:max_links]]