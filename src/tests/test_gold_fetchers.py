from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collectors.gold.instrument_sync import sync_gold_instruments_to_pg
from src.collectors.gold.models import BestLimitEntry, MarketWatchItem, TradeEntry
from src.collectors.gold.order_book_fetcher import (
    backfill_gold_order_books,
    fetch_gold_order_book_for_date,
    get_active_gold_codes,
)
from src.collectors.gold.trade_fetcher import (
    backfill_gold_trades,
    fetch_gold_trades_for_date,
)


@pytest.mark.asyncio
async def test_get_active_gold_codes():
    with patch("src.collectors.gold.order_book_fetcher.SessionLocal") as mock_session_local:
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session
        mock_session.execute.return_value.all.return_value = [("gld1",), ("gld2",)]

        codes = await get_active_gold_codes()
        assert codes == ["gld1", "gld2"]


@pytest.mark.asyncio
async def test_fetch_gold_order_book_for_date():
    client = AsyncMock()
    client.get_best_limits.return_value = [
        BestLimitEntry(
            h_even=60123,
            ref_id=15174976313,
            depth_level=1,
            bid_price=24000.0,
            bid_volume=1000,
            bid_order_count=5,
            ask_price=24500.0,
            ask_volume=790,
            ask_order_count=3,
        ),
    ]
    with patch("src.collectors.gold.order_book_fetcher.insert_gold_order_book") as mock_insert:
        result = await fetch_gold_order_book_for_date(client, "gld1", date(2026, 8, 29))
        assert result == 1
        mock_insert.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_gold_trades_for_date():
    client = AsyncMock()
    client.get_trade_history.return_value = [
        TradeEntry(h_even=60123, n_tran=1, price=24000.0, volume=100, canceled=False)
    ]
    with patch("src.collectors.gold.trade_fetcher.insert_gold_trades") as mock_insert:
        result = await fetch_gold_trades_for_date(client, "gld1", date(2026, 8, 29))
        assert result == 1
        mock_insert.assert_called_once()


@pytest.mark.asyncio
async def test_sync_gold_instruments_to_pg():
    client = AsyncMock()
    client.get_market_watch.return_value = [
        MarketWatchItem(ins_code="123", instrument_id="GLD1", symbol="عیار", name="صندوق طلا عیار", flow_code="1"),
        MarketWatchItem(ins_code="456", instrument_id="STK1", symbol="فولاد", name="فولاد مبارکه", flow_code="1"),
    ]
    client.get_instrument_info.return_value = None

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.text = """
    <table>
      <tr><td>طلا</td><td>عیار</td><td><a href="instInfo/123">Link</a></td></tr>
    </table>
    """

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with patch("src.collectors.gold.instrument_sync._upsert_instrument") as mock_upsert:
            res = await sync_gold_instruments_to_pg(client=client)
            assert res["synced"] == 1
            assert res["errors"] == []
            mock_upsert.assert_called_once()
