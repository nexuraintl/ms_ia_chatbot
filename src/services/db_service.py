import logging
from sqlalchemy import text
# Importamos el engine ya configurado en database.py para reusar el pool de conexiones
from src.database import engine

# Configuración de logs
logger = logging.getLogger(__name__)

async def search_internal_publications(user_query: str, limit: int = 3):
    """
    Busca publicaciones en la BD local usando Full-Text Search.
    Optimizado para no saturar el contexto de la IA.
    """
    # Usamos MATCH AGAINST para aprovechar el índice FULLTEXT creado
    query_sql = text("""
        SELECT nombre, texto, 
               MATCH(nombre, texto) AGAINST (:query IN NATURAL LANGUAGE MODE) AS relevance
        FROM publicaciones 
        WHERE MATCH(nombre, texto) AGAINST (:query IN NATURAL LANGUAGE MODE)
        ORDER BY relevance DESC
        LIMIT :limit
    """)
    
    try:
        async with engine.connect() as conn:
            result = await conn.execute(query_sql, {
                "query": user_query, 
                "limit": limit
            })
            
            # fetchall() devuelve objetos Row de SQLAlchemy
            rows = result.fetchall()
            
            # Procesamos resultados
            publications = []
            for row in rows:
                # Recortamos el texto a los primeros 3000 caracteres 
                # para evitar exceder límites de tokens en Gemini
                clean_text = (row.texto[:3000] + '...') if len(row.texto) > 3000 else row.texto
                
                publications.append({
                    "nombre": row.nombre,
                    "texto": clean_text
                })
            
            logger.info(f"DB_SEARCH: Se encontraron {len(publications)} coincidencias para: '{user_query[:30]}...'")
            return publications

    except Exception as e:
        # Importante: Logueamos el error pero no rompemos el flujo del Chat
        logger.error(f"DB_SEARCH_ERROR: Fallo al consultar MySQL: {str(e)}")
        return []