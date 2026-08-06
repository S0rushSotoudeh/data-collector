from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collectors.stock.market_watch_client import StockTsetmcClient


def _build_market_watch_text(rows: list[str]) -> str:
    return "@" * 2 + ";".join(rows) + "@" + "0@0@"


class TestGetMarketWatch:
    @pytest.fixture
    async def client(self) -> StockTsetmcClient:
        async with StockTsetmcClient(concurrency=10, retries=3, timeout=5) as c:
            yield c

    async def test_parses_stock_rows(self, client: StockTsetmcClient) -> None:
        row1 = "35100368959864864,IRO1FOLD0001,فولاد,فولاد مباركه اصفهان,122858,24000"
        row1_full = row1 + "," + ",".join([""] * 19) + ",1A"
        row2 = "123456,IRO2,پارس,سپنتا,x,y"
        row2_full = row2 + "," + ",".join([""] * 19) + ",1A"
        text = _build_market_watch_text([row1_full, row2_full])

        with patch.object(client._legacy_client, "get", AsyncMock(return_value=MagicMock(
            status_code=200,
            text=text,
        ))):
            items = await client.get_market_watch()

        assert len(items) == 2
        assert items[0].ins_code == "35100368959864864"
        assert items[0].instrument_id == "IRO1FOLD0001"
        assert items[0].symbol == "فولاد"
        assert items[0].name == "فولاد مباركه اصفهان"
        assert items[0].flow_code == "1A"
        assert items[1].ins_code == "123456"

    async def test_empty_response(self, client: StockTsetmcClient) -> None:
        with patch.object(client._legacy_client, "get", AsyncMock(return_value=MagicMock(
            status_code=200,
            text="",
        ))):
            items = await client.get_market_watch()
        assert items == []

    async def test_none_response(self, client: StockTsetmcClient) -> None:
        with patch.object(client._legacy_client, "get", AsyncMock(return_value=MagicMock(
            status_code=404,
            text="",
        ))):
            items = await client.get_market_watch()
        assert items == []

    async def test_short_rows_skipped(self, client: StockTsetmcClient) -> None:
        text = _build_market_watch_text(["a,b,c", "1,2,3,4,5"])
        with patch.object(client._legacy_client, "get", AsyncMock(return_value=MagicMock(
            status_code=200,
            text=text,
        ))):
            items = await client.get_market_watch()
        assert len(items) == 1
        assert items[0].ins_code == "1"
