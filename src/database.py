from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.config import settings

# Verificación de integridad
if not all([settings.DB_USER, settings.DB_PASSWORD, settings.DB_NAME]):
    raise ValueError("Faltan variables de entorno críticas para la conexión a la base de datos.")

# Motor asíncrono corregido
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    pool_pre_ping=True, # Verifica si la conexión sigue viva antes de usarla
    connect_args={"connect_timeout": 5}, # <--- Corregido el typo 'cconnect'
    echo=False
)

async_session = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def get_db_session():
    async with async_session() as session:
        yield session