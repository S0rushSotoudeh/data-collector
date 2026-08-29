from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from src.admin import create_admin
from src.config import env
from src.admin.auth import BasicAuthBackend
from src.routes.admin_tasks import router as admin_tasks_router
from src.routes.yield_curve import router as yield_curve_router
from src.routes.yield_spread import router as yield_spread_router
from src.routes.bond_trades_values import router as bond_trades_values_router
from src.routes.option_market_data import router as option_market_data_router
from src.routes.stock_market_data import router as stock_router
from src.routes.parity_analysis import router as parity_analysis_router
from src.routes.iv_surface import router as iv_surface_router
from src.routes.market_potential import router as market_potential_router
from src.routes.box_spread import router as box_spread_router
from src.routes.option_mispricing import router as option_mispricing_router
from src.routes.ime import router as ime_router
from src.routes.gold_market_data import router as gold_router

_SECRET_KEY = env("SECRET_KEY")

app = FastAPI(
    title="Data Collector API",
    description="Real-time market data collection and analytics for HFT research.",
    version="0.1.0",
)

app.add_middleware(SessionMiddleware, secret_key=_SECRET_KEY)

_auth_backend = BasicAuthBackend(secret_key=_SECRET_KEY)
app.state.auth_backend = _auth_backend

app.include_router(admin_tasks_router, prefix="")
app.include_router(yield_curve_router, prefix="")
app.include_router(yield_spread_router, prefix="")
app.include_router(bond_trades_values_router, prefix="")
app.include_router(option_market_data_router, prefix="")
app.include_router(stock_router, prefix="")
app.include_router(parity_analysis_router, prefix="")
app.include_router(iv_surface_router, prefix="")
app.include_router(market_potential_router, prefix="")
app.include_router(box_spread_router, prefix="")
app.include_router(option_mispricing_router, prefix="")
app.include_router(ime_router, prefix="")
app.include_router(gold_router, prefix="")


@app.get("/admin/data-collection-run/list", include_in_schema=False)
async def legacy_collection_runs_redirect():
    return RedirectResponse("/admin/collection-runs", status_code=307)

# Register the catch-all admin mount after API routers so /admin/tasks routes
# are matched by their explicit handlers rather than the admin 404 fallback.
create_admin(app, _auth_backend)


@app.get("/")
async def root():
    return {"message": "Hello, HFT World!", "status": "alive"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
