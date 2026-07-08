import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from src.admin import create_admin
from src.admin.auth import BasicAuthBackend
from src.routes.admin_tasks import router as admin_tasks_router
from src.routes.yield_curve import router as yield_curve_router
from src.routes.yield_spread import router as yield_spread_router
from src.routes.bond_trades_values import router as bond_trades_values_router
from src.routes.option_market_data import router as option_market_data_router
from src.routes.stock_market_data import router as stock_router

_SECRET_KEY = os.environ["SECRET_KEY"]

app = FastAPI(
    title="Data Collector API",
    description="Real-time market data collection and analytics for HFT research.",
    version="0.1.0",
)

app.add_middleware(SessionMiddleware, secret_key=_SECRET_KEY)

_auth_backend = BasicAuthBackend(secret_key=_SECRET_KEY)
app.state.auth_backend = _auth_backend
create_admin(app, _auth_backend)

app.include_router(admin_tasks_router, prefix="")
app.include_router(yield_curve_router, prefix="")
app.include_router(yield_spread_router, prefix="")
app.include_router(bond_trades_values_router, prefix="")
app.include_router(option_market_data_router, prefix="")
app.include_router(stock_router, prefix="")


@app.get("/")
async def root():
    return {"message": "Hello, HFT World!", "status": "alive"}


@app.get("/health")
async def health():
    return {"status": "healthy"}