from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app



@pytest.mark.asyncio
@patch("src.routes.gold_analytics.get_gold_order_book_micro_price_intraday", new_callable=AsyncMock)
@patch("src.routes.gold_analytics.intraday_best_quotes", new_callable=AsyncMock)
async def test_api_gold_normalized_spread_intraday(mock_get_certificates, mock_get_ob) -> None:
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
    mock_get_certificates.side_effect = [
        [{"trade_time": 120000, "best_bid": 2000.0, "best_ask": 2002.0}],
        [{"trade_time": 120000, "best_bid": 3000.0, "best_ask": 3000.0}],
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

        # Each instrument uses its own combined bid/ask min-max scale.
        assert pts1[0]["bid"] == 0.0
        assert 0 < pts1[0]["ask"] < 1
        assert pts2[0]["bid"] == 0.0
        assert 0 < pts2[0]["ask"] < 1

        assert pts1[1]["ask"] == 1.0
        assert pts2[1]["ask"] == 1.0
        assert data["instrument1"]["scale"] == {"min": 1000.0, "max": 1011.0}
        assert pts1[0]["bid_price"] == 1000.0
        assert [item["code"] for item in data["certificates"]] == ["GOLDBAR", "GOLDCOIN"]
        assert data["certificates"][0]["points"][0]["bid"] == 0.0
        assert data["certificates"][0]["points"][0]["ask"] == 1.0
        assert data["certificates"][1]["points"][0]["bid"] == 0.5
        assert data["certificates"][1]["points"][0]["ask"] == 0.5
        assert all(call.kwargs["from_time"] == 120000 for call in mock_get_ob.call_args_list)
        assert all(call.kwargs["to_time"] == 180000 for call in mock_get_ob.call_args_list)
        assert all(call.args[2:] == (120000, 180000) for call in mock_get_certificates.call_args_list)
