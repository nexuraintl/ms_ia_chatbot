import google.generativeai as genai
from src.config import settings

# Configuración única al importar el módulo
genai.configure(api_key=settings.GEMINI_API_KEY)

# Instanciamos el modelo
model = genai.GenerativeModel('gemini-2.5-flash')

async def generate_answer(question: str, context_text: str) -> str:
    """
    Genera una respuesta usando Gemini basada en el contexto proporcionado,
    prohibiendo explícitamente el uso de URLs.
    """
    # Hemos añadido instrucciones de restricción de formato y estilo.
    prompt = f"""
    Actúa como un asistente experto y servicial. Tu objetivo es responder la pregunta del usuario basándote exclusivamente en el contexto proporcionado.

    REGLAS CRÍTICAS DE RESPUESTA:
    1. ÚNICAMENTE usa la información del CONTEXTO para responder.
    2. PROHIBICIÓN TOTAL DE URLs: No incluyas enlaces, direcciones web, rutas de archivos ni URLs en tu respuesta, incluso si aparecen en el contexto.
    3. NO MENCIONES LA FUENTE: No digas frases como "según el texto", "en la URL proporcionada" o "el contexto dice". Responde de forma directa como si fuera tu propio conocimiento.
    4. Si la información necesaria para responder no está en el contexto, responde amigablemente que no cuentas con esa información específica en este momento.

    CONTEXTO:
    {context_text}

    PREGUNTA:
    {question}
    """

    try:
        response = model.generate_content(prompt)
        # Limpieza adicional por si el modelo ignora el prompt (poco probable en 2.5 Flash)
        return response.text
    except Exception as e:
        return f"Error al procesar con Gemini: {str(e)}"