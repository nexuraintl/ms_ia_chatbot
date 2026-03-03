# src/routers/chat_router.py

from fastapi import APIRouter, HTTPException
from src.models.schemas import ChatRequest, ChatResponse
from src.services.scraper_service import scrape_url_with_context, scrape_specific_urls 
from src.services.gemini_service import generate_answer, is_context_sufficient # <-- Importamos validación
from src.services.db_service import search_internal_publications # <-- Importamos servicio DB

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    try:
        # 1. INTENTO INICIAL: Scraping Web
        if isinstance(payload.url, list):
            context_text = await scrape_specific_urls(payload.url)
        else:
            context_text = await scrape_url_with_context(str(payload.url), payload.question)

        # 2. VALIDACIÓN: ¿La web devolvió algo útil?
        # Usamos is_context_sufficient para que la IA decida si con lo que leyó puede responder
        suficiente = await is_context_sufficient(payload.question, context_text)

        internal_db_context = ""
        
        # 3. FALLBACK: Si no es suficiente, consultamos la base de datos interna
        if not suficiente:
            print(f"DEBUG: Contexto web insuficiente. Consultando base de datos interna...")
            publicaciones = await search_internal_publications(payload.question)
            
            # Formateamos los resultados de la BD para inyectarlos al prompt
            if publicaciones:
                internal_db_context = "\n".join([
                    f"Título interno: {p['nombre']}\nContenido interno: {p['texto']}" 
                    for p in publicaciones
                ])
            else:
                print("DEBUG: No se encontraron coincidencias en la base de datos.")

        # 4. GENERACIÓN FINAL: Gemini recibe contexto web + contexto BD (si existe)
        answer = await generate_answer(
            question=payload.question, 
            context_text=context_text, 
            internal_db_context=internal_db_context
        )

        return ChatResponse(answer=answer, source_url=str(payload.url))

    except Exception as e:
        # Log del error para Cloud Logging antes de lanzar la excepción
        print(f"ERROR en chat_endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno procesando la solicitud.")