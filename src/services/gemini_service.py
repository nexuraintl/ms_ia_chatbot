import google.generativeai as genai
from src.config import settings
from typing import List, Tuple

genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

async def is_context_sufficient(question: str, context_text: str) -> bool:
    """
    Determina si el contexto web es suficiente.
    """
    # Si no hay texto web, devolvemos False de inmediato para ir a la BD
    if not context_text or len(context_text.strip()) < 100:
        return False

    prompt = f"""
    ¿El siguiente CONTEXTO tiene información suficiente para responder a la PREGUNTA?
    Responde estrictamente SI o NO.

    PREGUNTA: {question}
    CONTEXTO: {context_text[:2000]}
    """
    try:
        response = model.generate_content(prompt)
        return "SI" in response.text.upper()
    except:
        return False # Ante error de API, intentamos por si acaso con BD

async def generate_answer(question: str, context_text: str, internal_db_context: str = "") -> str:
    """
    Genera respuesta integrando fuentes web e internas.
    """
    
    # Construcción dinámica del bloque de contexto para la IA
    context_blocks = []
    if context_text and len(context_text.strip()) > 10:
        context_blocks.append(f"--- INFORMACIÓN WEB ---\n{context_text}")
    
    if internal_db_context and len(internal_db_context.strip()) > 10:
        context_blocks.append(f"--- INFORMACIÓN INTERNA (BASE DE DATOS) ---\n{internal_db_context}")

    # Si no hay absolutamente nada de información
    if not context_blocks:
        return "Lo siento, no encontré información relevante en nuestras fuentes para responder a tu pregunta."

    full_context = "\n\n".join(context_blocks)

    prompt = f"""
    Eres un asistente experto de atención al ciudadano. 
    Responde la PREGUNTA usando exclusivamente el CONTEXTO proporcionado.

    REGLAS DE RESPUESTA:
    1. Si hay "Información Institucional Interna", dales prioridad para trámites específicos.
    2. Responde de forma cordial y profesional.
    3. PROHIBICIÓN: No incluyas URLs, enlaces ni correos electrónicos.
    4. PROHIBICIÓN: No digas "según la base de datos" o "en el sitio web".
    5. Si la información no es suficiente en ninguno de los contextos, responde: 
       "Lo siento, no tengo información suficiente para responder a esa pregunta específica. Por favor, intenta con otros términos."

    CONTEXTO:
    {full_context}

    PREGUNTA:
    {question}
    """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Lo siento, ocurrió un error al procesar la respuesta. (Error: {str(e)})"

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