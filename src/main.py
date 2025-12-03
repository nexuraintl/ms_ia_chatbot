from fastapi import FastAPI
from src.routers import chat_router

app = FastAPI(
    title="Gemini URL Chatbot Microservice",
    version="1.0.0"
)

app.include_router(chat_router.router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok"}