# Usamos una imagen base ligera de Python
FROM python:3.10-slim

# Evita archivos .pyc y asegura que los logs lleguen a Cloud Logging inmediatamente
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instalamos dependencias de sistema necesarias para drivers de BD y certificados
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalamos dependencias (Copiamos primero para aprovechar el caché de capas de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código
COPY . .

# Puerto por defecto de Cloud Run
ENV PORT=8080

# Ejecución profesional: Gunicorn con worker de Uvicorn para alta concurrencia asíncrona
# --workers 1: En Cloud Run se recomienda 1 worker por instancia ya que GCP gestiona el escalado.
# --timeout 0: Desactiva el timeout de gunicorn para dejar que Cloud Run gestione el ciclo de vida.
CMD exec gunicorn --bind :$PORT --workers 1 --worker-class uvicorn.workers.UvicornWorker --timeout 0 app:app