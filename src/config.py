import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        # Esto lanzará error al arrancar si falta la key, previniendo fallos silenciosos
        raise ValueError("GEMINI_API_KEY no está configurada en las variables de entorno.")

settings = Config()