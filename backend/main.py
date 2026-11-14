"""Compatibility entry point: python main.py or uvicorn main:app."""

from app.main import app as app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
