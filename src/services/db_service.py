import logging
from sqlalchemy import text
from src.database import engine

logger = logging.getLogger(__name__)

async def search_internal_publications(user_query: str, limit: int = 3):
    """
    Busca publicaciones en la BD local usando Full-Text Search.
    """
    # Validamos que haya una consulta válida para no disparar errores de MySQL
    if not user_query or len(user_query.strip()) < 3:
        return []

    query_sql = text("""
        SELECT nombre, texto, 
               MATCH(nombre, texto) AGAINST (:query IN NATURAL LANGUAGE MODE) AS relevance
        FROM publicaciones 
        WHERE MATCH(nombre, texto) AGAINST (:query IN NATURAL LANGUAGE MODE)
        ORDER BY relevance DESC
        LIMIT :limit
    """)
    
    try:
        # Usamos engine.connect() en un bloque asíncrono
        async with engine.connect() as conn:
            result = await conn.execute(query_sql, {
                "query": user_query, 
                "limit": limit
            })
            
            # Obtenemos los nombres de las columnas para un mapeo seguro
            # Esto evita errores si row no permite acceso por atributo
            rows = result.mappings().all()
            
            publications = []
            for row in rows:
                content = row['texto'] if row['texto'] else ""
                # Recorte de seguridad para tokens (3000 chars aprox 750 tokens)
                clean_text = (content[:3000] + '...') if len(content) > 3000 else content
                
                publications.append({
                    "nombre": row['nombre'],
                    "texto": clean_text
                })
            
            logger.info(f"DB_SEARCH: {len(publications)} resultados obtenidos para la consulta.")
            return publications

    except Exception as e:
        # Diferenciamos errores de conexión (VPC/Firewall) de errores de SQL
        error_msg = str(e).lower()
        if "connection" in error_msg or "timeout" in error_msg:
            logger.error(f"DB_NETWORK_ERROR: No se pudo alcanzar el servidor MySQL vía VPC. Verifica el conector y firewall. Error: {e}")
        else:
            logger.error(f"DB_QUERY_ERROR: Error en la consulta o estructura de la tabla. Error: {e}")
        
        # Cumplimos con tu requerimiento: Si falla la BD, devolvemos vacío para usar solo URL
        return []