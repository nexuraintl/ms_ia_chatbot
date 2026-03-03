import google.generativeai as genai
from src.config import settings
from typing import List, Tuple

# Configuración única
genai.configure(api_key=settings.GEMINI_API_KEY)

# Instanciamos el modelo
model = genai.GenerativeModel('gemini-2.0-flash')

async def is_context_sufficient(question: str, context_text: str) -> bool:
    """
    NUEVA: Determina si el contexto web es suficiente para responder.
    Esto evita consultas innecesarias a la BD si la web ya tiene la respuesta.
    """
    if not context_text or len(context_text) < 100:
        return False

    prompt = f"""
    Analiza si el siguiente CONTEXTO contiene información suficiente para responder a la PREGUNTA.
    Responde ÚNICAMENTE con la palabra 'SI' o 'NO'.

    PREGUNTA: {question}
    CONTEXTO: {context_text[:2000]} # Solo enviamos una muestra para ahorrar tokens
    """
    try:
        response = model.generate_content(prompt)
        return "SI" in response.text.upper()
    except:
        return False

async def generate_answer(question: str, context_text: str, internal_db_context: str = "") -> str:
    """
    Genera una respuesta basada en contexto Web e Interno.
    """
    # Combinamos contextos si existe información de la BD
    full_context = context_text
    if internal_db_context:
        full_context += f"\n\nINFORMACIÓN ADICIONAL DE BASE DE DATOS INTERNA:\n{internal_db_context}"

    prompt = f"""
    Actúa como un asistente experto. Responde basándote exclusivamente en el contexto.

    REGLAS CRÍTICAS:
    1. Prioriza la información más reciente o relevante entre el contexto web y la base de datos.
    2. PROHIBICIÓN TOTAL DE URLs.
    3. NO MENCIONES LAS FUENTES (ej. no digas "según la base de datos").
    4. Si después de usar ambos contextos no tienes la información, admítelo amigablemente.

    CONTEXTO TOTAL:
    {full_context}

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