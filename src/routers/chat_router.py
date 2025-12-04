# src/routers/chat_router.py

from fastapi import APIRouter, HTTPException
from src.models.schemas import ChatRequest, ChatResponse
# --- CAMBIO AQUÍ: Importamos la nueva función ---
from src.services.scraper_service import scrape_url_with_context 
from src.services.gemini_service import generate_answer

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    try:
        # 1. Obtener contexto de la URL (Ahora rastrea múltiples páginas)
        context_text = await scrape_url_with_context(str(payload.url)) 
        
        if not context_text:
            # Este error ahora es más específico si el rastreo inicial falla
            raise HTTPException(status_code=400, detail="No se pudo obtener contexto de la URL o sus páginas relacionadas.")

        # 2. Consultar a Gemini (La función recibe el texto masivo)
        answer = await generate_answer(payload.question, context_text)

        return ChatResponse(
            answer=answer,
            source_url=str(payload.url)
        )

    except Exception as e:
        # Manejo de errores generales
        raise HTTPException(status_code=500, detail=str(e))