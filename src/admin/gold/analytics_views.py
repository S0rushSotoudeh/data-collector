from typing import Any

from sqladmin import BaseView, expose
from sqlmodel import select
from starlette.requests import Request
from starlette.responses import HTMLResponse

from src.admin._render import _render
from src.db.models.stock import StockInstrument
from src.db.session import SessionLocal


class GoldBestQuotesChartView(BaseView):
    name = "Gold Best Quotes"
    identity = "gold-best-quotes"
    icon = "fa-solid fa-chart-line"
    category = "Gold Analytics"
    category_icon = "fa-solid fa-coins"

    @expose("/gold-best-quotes", methods=["GET"])
    async def gold_best_quotes(self, request: Request) -> HTMLResponse:
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
            "title": "Gold Best Quotes",
            "subtitle": "Raw Best Bid & Best Ask prices for two gold ETF instruments",
            "instruments": instruments,
        }
        ctx["url_for"] = lambda name, **params: request.url_for(name, **params)
        return HTMLResponse(_render("gold/gold_price_comparison.html", ctx))

