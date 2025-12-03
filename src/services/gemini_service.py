import google.generativeai as genai
from src.config import settings

# Configuración única al importar el módulo
genai.configure(api_key=settings.GEMINI_API_KEY)

# Instanciamos el modelo (Gemini 1.5 Flash es ideal para esto por velocidad)
model = genai.GenerativeModel('gemini-1.5-flash')

async def generate_answer(question: str, context_text: str) -> str:
    """
    Genera una respuesta usando Gemini basada en el contexto proporcionado.
    """
    prompt = f"""
    Actúa como un asistente experto. Responde a la siguiente pregunta basándote ÚNICAMENTE en el contexto proporcionado a continuación.
    Si la respuesta no se encuentra en el contexto, indica que no tienes información suficiente en esa URL.

    CONTEXTO:
    {context_text}

    PREGUNTA:
    {question}
    """

    try:
        # generate_content es sincrono en esta versión del SDK, pero rápido.
        # Si la carga es muy alta, se puede ejecutar en un threadpool, 
        # pero para Cloud Run estándar esto es aceptable.
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error al procesar con Gemini: {str(e)}"