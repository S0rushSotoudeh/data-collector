from typing import Any

from sqladmin import BaseView, expose
from sqlmodel import select
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _render
from src.db.models.stock import StockInstrument
from src.db.session import SessionLocal


class GoldPriceComparisonChartView(BaseView):
    name = "Gold Price Comparison"
    identity = "gold-price-comparison"
    icon = "fa-solid fa-chart-line"
    category = "Gold Analytics"
    category_icon = "fa-solid fa-coins"

    @expose("/gold-price-comparison", methods=["GET"])
    async def gold_price_comparison(self, request: Request) -> HTMLResponse:
        instruments: list[dict[str, str]] = []
        with SessionLocal() as session:
            stmt = (
                select(StockInstrument)
                .where(StockInstrument.is_gold_etf.is_(True))
                .order_by(StockInstrument.symbol.asc())
            )
            golds = session.execute(stmt).scalars().all()
            for g in golds:
                instruments.append({
                    "instrument_code": g.instrument_code,
                    "symbol": g.symbol or g.instrument_code,
                    "name_fa": g.name_fa or "",
                })

        ctx: dict[str, Any] = {
            "request": request,
            "admin": self._admin_ref,
            "title": "Gold Price Comparison",
            "subtitle": "Compare real trade prices of two gold ETF instruments on one chart",
            "instruments": instruments,
        }
        ctx["url_for"] = lambda name, **params: request.url_for(name, **params)
        return HTMLResponse(_render("gold/gold_price_comparison.html", ctx))


class GoldKalmanArbitrageChartView(BaseView):
    name = "Gold Kalman Arbitrage"
    identity = "gold-kalman-arbitrage"
    icon = "fa-solid fa-calculator"
    category = "Gold Analytics"
    category_icon = "fa-solid fa-coins"

    @expose("/gold-kalman-arbitrage", methods=["GET"])
    async def gold_kalman_arbitrage(self, request: Request) -> HTMLResponse:
        instruments: list[dict[str, str]] = []
        with SessionLocal() as session:
            stmt = (
                select(StockInstrument)
                .where(StockInstrument.is_gold_etf.is_(True))
                .order_by(StockInstrument.symbol.asc())
            )
            golds = session.execute(stmt).scalars().all()
            for g in golds:
                instruments.append({
                    "instrument_code": g.instrument_code,
                    "symbol": g.symbol or g.instrument_code,
                    "name_fa": g.name_fa or "",
                })

        ctx: dict[str, Any] = {
            "request": request,
            "admin": self._admin_ref,
            "title": "Gold Kalman Filter Arbitrage",
            "subtitle": "Online Kalman filter dynamic hedge ratio, latent spread & normalized Z-score",
            "instruments": instruments,
        }
        ctx["url_for"] = lambda name, **params: request.url_for(name, **params)
        return HTMLResponse(_render("gold/gold_kalman_arbitrage.html", ctx))
