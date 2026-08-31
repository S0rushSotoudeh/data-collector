from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.admin.gold.analytics_views import GoldKalmanArbitrageChartView
from src.analytics.gold_kalman import run_gold_kalman_filter
from src.main import app


def test_gold_kalman_views_properties() -> None:
    assert GoldKalmanArbitrageChartView.category == "Gold Analytics"
    assert GoldKalmanArbitrageChartView.identity == "gold_kalman_arbitrage"


def test_run_gold_kalman_filter_mathematics() -> None:
    times = [120000 + i * 5 for i in range(100)]
    prices2 = [100.0 + i * 0.1 for i in range(100)]
    # p1 = 2 * p2 with slight noise
    prices1 = [2.0 * p + (0.5 if i % 2 == 0 else -0.5) for i, p in enumerate(prices2)]

    res = run_gold_kalman_filter(prices1, prices2, times)
    assert len(res["times"]) == 100
    assert len(res["beta"]) == 100
    assert len(res["z_score"]) == 100
    assert len(res["p1_norm"]) == 100
    assert len(res["p2_norm"]) == 100
    # Initial normalized prices start at 100
    assert res["p1_norm"][0] == 100.0
    assert res["p2_norm"][0] == 100.0
    # Z-scores are bounded in a reasonable range
    for z in res["z_score"]:
        assert -10.0 <= z <= 10.0


def test_run_gold_kalman_filter_empty() -> None:
    res = run_gold_kalman_filter([], [], [])
    assert res["times"] == []
    assert res["z_score"] == []


@pytest.mark.asyncio
@patch("src.routes.gold_analytics.get_gold_order_book_micro_price_intraday", new_callable=AsyncMock)
async def test_api_gold_kalman_arbitrage_micro_price(mock_get_ob) -> None:
    mock_get_ob.side_effect = [
        [
            {"trade_time": 120000, "price": 1000.0},
            {"trade_time": 120005, "price": 1010.0},
        ],
        [
            {"trade_time": 120000, "price": 500.0},
            {"trade_time": 120005, "price": 505.0},
        ],
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get(
            "/api/v1/gold-analytics/kalman-arbitrage/intraday?instrument1=G1&instrument2=G2&date=2026-08-01&price_source=orderbook_micro"
        )
        assert res.status_code == 200
        data = res.json()
        assert data["trade_date"] == "2026-08-01"
        assert data["price_source"] == "orderbook_micro"
        assert len(data["results"]["times"]) == 2
        assert len(data["results"]["z_score"]) == 2
        assert len(data["results"]["beta"]) == 2


@pytest.mark.asyncio
@patch("src.routes.gold_analytics.get_gold_trades_comparison_intraday", new_callable=AsyncMock)
async def test_api_gold_kalman_arbitrage_trades(mock_get_trades) -> None:
    mock_get_trades.side_effect = [
        [
            {"trade_time": 120000, "price": 1000.0, "value": 50000.0},
            {"trade_time": 120005, "price": 1010.0, "value": 50000.0},
        ],
        [
            {"trade_time": 120000, "price": 500.0, "value": 25000.0},
            {"trade_time": 120005, "price": 505.0, "value": 25000.0},
        ],
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get(
            "/api/v1/gold-analytics/kalman-arbitrage/intraday?instrument1=G1&instrument2=G2&date=2026-08-01&price_source=trades"
        )
        assert res.status_code == 200
        data = res.json()
        assert data["trade_date"] == "2026-08-01"
        assert data["price_source"] == "trades"
        assert len(data["results"]["times"]) == 2
