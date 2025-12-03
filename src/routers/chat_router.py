from fastapi import APIRouter, HTTPException
from src.models.schemas import ChatRequest, ChatResponse
from src.services.scraper_service import scrape_url
from src.services.gemini_service import generate_answer

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    try:
        # 1. Obtener contexto de la URL
        context_text = await scrape_url(str(payload.url))
        
        if not context_text:
            raise HTTPException(status_code=400, detail="No se pudo extraer texto de la URL proporcionada.")

        # 2. Consultar a Gemini
        answer = await generate_answer(payload.question, context_text)

        return ChatResponse(
            answer=answer,
            source_url=str(payload.url)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))