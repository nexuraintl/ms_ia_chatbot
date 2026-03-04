import logging
from sqlalchemy import text
from src.database import engine
from bs4 import BeautifulSoup # Importante para limpiar el HTML de la BD

logger = logging.getLogger(__name__)

async def search_internal_publications(user_query: str, limit: int = 3):
    """
    Busca en tn_pub_publm usando los campos reales y limpia el HTML.
    """
    if not user_query or len(user_query.strip()) < 3:
        return []

    # Ajustado a tu tabla tn_pub_publm y columnas reales
    query_sql = text("""
        SELECT titulo, resumen, texto, 
               MATCH(titulo, resumen, texto) AGAINST (:query IN NATURAL LANGUAGE MODE) AS relevance
        FROM tn_pub_publm 
        WHERE MATCH(titulo, resumen, texto) AGAINST (:query IN NATURAL LANGUAGE MODE)
        ORDER BY relevance DESC
        LIMIT :limit
    """)
    
    try:
        async with engine.connect() as conn:
            result = await conn.execute(query_sql, {
                "query": user_query, 
                "limit": limit
            })
            
            rows = result.mappings().all()
            publications = []
            
            for row in rows:
                # Combinamos resumen y texto
                raw_html = f"{row['resumen'] or ''} {row['texto'] or ''}"
                
                # --- LIMPIEZA DE HTML ---
                # Extraemos solo el texto para no gastar tokens en etiquetas <div>, <span>, etc.
                soup = BeautifulSoup(raw_html, "html.parser")
                clean_text = soup.get_text(separator=" ", strip=True)
                
                # Recorte de seguridad (4000 caracteres son aprox 1000 tokens)
                final_text = (clean_text[:4000] + '...') if len(clean_text) > 4000 else clean_text
                
                publications.append({
                    "nombre": row['titulo'], # Mantenemos la llave 'nombre' para gemini_service
                    "texto": final_text
                })
            
            logger.info(f"DB_SEARCH: {len(publications)} resultados reales de tn_pub_publm")
            return publications

    except Exception as e:
        logger.error(f"DB_ERROR: {str(e)}")
        return []