from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.admin.gold.analytics_views import GoldBestQuotesChartView
from src.main import app


def test_gold_analytics_views_properties() -> None:
    assert GoldBestQuotesChartView.category == "Gold Analytics"
    assert GoldBestQuotesChartView.identity == "gold_best_quotes"


@pytest.mark.asyncio
@patch("src.routes.gold_analytics.get_gold_order_book_micro_price_intraday", new_callable=AsyncMock)
async def test_api_gold_compare_intraday(mock_get_intraday) -> None:
    mock_get_intraday.side_effect = [
        [{"trade_time": 120000, "price": 1000.0, "best_bid": 999.0, "best_ask": 1001.0}],
        [{"trade_time": 120000, "price": 1050.0, "best_bid": 1049.0, "best_ask": 1051.0}],
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/v1/gold-analytics/compare/intraday?instrument1=G1&instrument2=G2&date=2026-08-01")
        assert res.status_code == 200
        data = res.json()
        assert data["trade_date"] == "2026-08-01"
        assert len(data["instrument1"]["points"]) == 1
        assert len(data["instrument2"]["points"]) == 1
        assert data["instrument1"]["points"][0]["price"] == 1000.0
        assert data["instrument2"]["points"][0]["price"] == 1050.0


@pytest.mark.asyncio
@patch("src.routes.gold_analytics.get_stock_trades_daily", new_callable=AsyncMock)
async def test_api_gold_compare_daily(mock_get_daily) -> None:
    mock_get_daily.side_effect = [
        [{"trade_date": "2026-08-01", "value": 1000.0}],
        [{"trade_date": "2026-08-01", "value": 1050.0}],
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/v1/gold-analytics/compare/daily?instrument1=G1&instrument2=G2&from=2026-08-01&to=2026-08-05")
        assert res.status_code == 200
        data = res.json()
        assert data["from"] == "2026-08-01"
        assert data["to"] == "2026-08-05"
        assert len(data["instrument1"]["days"]) == 1
        assert len(data["instrument2"]["days"]) == 1
