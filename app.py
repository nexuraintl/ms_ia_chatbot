from src.main import app

if __name__ == "__main__":
    import uvicorn
    # Esto permite correrlo localmente con: python app.py
    uvicorn.run(app, host="0.0.0.0", port=8080)