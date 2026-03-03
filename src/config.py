import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY no está configurada.")

    # Variables de Base de Datos
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")  # Default a localhost si no existe
    DB_PORT = os.getenv("DB_PORT", "3306")       # Default puerto MySQL
    DB_NAME = os.getenv("DB_NAME")

    @property
    def DATABASE_URL(self):
        # Usamos @property para que se genere dinámicamente al llamar a settings.DATABASE_URL
        # Importante usar el driver aiomysql para asincronía
        return f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

settings = Config()