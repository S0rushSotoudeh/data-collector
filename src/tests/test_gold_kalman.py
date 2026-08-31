from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.admin.gold.analytics_views import GoldNormalizedSpreadChartView
from src.main import app


def test_gold_normalized_spread_view_properties() -> None:
    assert GoldNormalizedSpreadChartView.category == "Gold Analytics"
    assert GoldNormalizedSpreadChartView.identity == "gold_normalized_spread"


@pytest.mark.asyncio
@patch("src.routes.gold_analytics.get_gold_order_book_micro_price_intraday", new_callable=AsyncMock)
async def test_api_gold_normalized_spread_intraday(mock_get_ob) -> None:
    mock_get_ob.side_effect = [
        [
            {"trade_time": 120000, "best_bid": 1000.0, "best_ask": 1001.0},
            {"trade_time": 120005, "best_bid": 1010.0, "best_ask": 1011.0},
        ],
        [
            {"trade_time": 120000, "best_bid": 500.0, "best_ask": 501.0},
            {"trade_time": 120005, "best_bid": 505.0, "best_ask": 506.0},
        ],
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get(
            "/api/v1/gold-analytics/normalized-spread/intraday?instrument1=G1&instrument2=G2&date=2026-08-01"
        )
        assert res.status_code == 200
        data = res.json()
        assert data["trade_date"] == "2026-08-01"

        pts1 = data["instrument1"]["points"]
        pts2 = data["instrument2"]["points"]
        assert len(pts1) == 2
        assert len(pts2) == 2

        # First point log return starts at 0.0
        assert pts1[0]["bid"] == 0.0
        assert pts1[0]["ask"] == 0.0
        assert pts2[0]["bid"] == 0.0
        assert pts2[0]["ask"] == 0.0

        # Second point log return is positive (price went up)
        assert pts1[1]["bid"] > 0
        assert pts2[1]["bid"] > 0
