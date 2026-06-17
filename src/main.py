import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from src.admin import create_admin
from src.admin.auth import BasicAuthBackend

_SECRET_KEY = os.environ["SECRET_KEY"]

app = FastAPI(
    title="Data Collector API",
    description="Real-time market data collection and analytics for HFT research.",
    version="0.1.0",
)

app.add_middleware(SessionMiddleware, secret_key=_SECRET_KEY)

_auth_backend = BasicAuthBackend(secret_key=_SECRET_KEY)
create_admin(app, _auth_backend)


@app.get("/")
async def root():
    return {"message": "Hello, HFT World!", "status": "alive"}


@app.get("/health")
async def health():
    return {"status": "healthy"}