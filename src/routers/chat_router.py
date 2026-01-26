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
        # Verificamos si es una lista o un solo string
        if isinstance(payload.url, list):
            print(f"DEBUG: Modo Selección Directa detectado ({len(payload.url)} URLs)")
            # Nueva función para procesar la lista exacta
            context_text = await scrape_specific_urls(payload.url)
        else:
            print(f"DEBUG: Modo Explorador detectado (URL única)")
            # Tu función actual que busca el mapa del sitio
            context_text = await scrape_url_with_context(str(payload.url), payload.question)

        # Generar respuesta con Gemini (tu función actual)
        answer = await generate_answer(payload.question, context_text)

        return ChatResponse(answer=answer, source_url=str(payload.url))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))