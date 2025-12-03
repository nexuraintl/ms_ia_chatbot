# Usamos una imagen base ligera
FROM python:3.10-slim

# Evita que Python genere archivos .pyc y habilita logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalamos dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el código fuente
COPY . .

# Exponemos el puerto (Cloud Run inyecta la variable PORT, por defecto 8080)
ENV PORT=8080

# Comando de ejecución apuntando a app.py
CMD exec uvicorn app:app --host 0.0.0.0 --port $PORT