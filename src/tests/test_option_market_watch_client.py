from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.collectors.option.market_watch_client import (
    OptionTsetmcClient,
    OptionTsetmcError,
)


_SAMPLE_MARKET_WATCH = (
    "@"
    "@"
    "@1,2,3,4,5@0@0@"
)


def _build_market_watch_text(rows: list[str]) -> str:
    return "@" * 2 + ";".join(rows) + "@" + "0@0@"


class TestGetMarketWatch:
    @pytest.fixture
    async def client(self) -> OptionTsetmcClient:
        async with OptionTsetmcClient(concurrency=10, retries=3, timeout=5) as c:
            yield c

    async def test_parses_option_rows(self, client: OptionTsetmcClient) -> None:
        row1 = "3729523725493580,IRO9AHRM0A01,ضهرم4023,اختیارخ اهرم-20000-1405/04/31,122858,24000"
        row1_full = row1 + "," + ",".join([""] * 19) + ",3A"
        row2 = "123456,IRO2,ضت1,اختیارف تپکو-1000-1405/04/31,x,y"
        row2_full = row2 + "," + ",".join([""] * 19) + ",3A"
        text = _build_market_watch_text([row1_full, row2_full])

        with patch.object(client._legacy_client, "get", AsyncMock(return_value=MagicMock(
            status_code=200,
            text=text,
        ))):
            items = await client.get_market_watch()

        assert len(items) == 2
        assert items[0].ins_code == "3729523725493580"
        assert items[0].instrument_id == "IRO9AHRM0A01"
        assert items[0].symbol == "ضهرم4023"
        assert items[0].name == "اختیارخ اهرم-20000-1405/04/31"
        assert items[0].flow_code == "3A"
        assert items[1].ins_code == "123456"

    async def test_empty_response(self, client: OptionTsetmcClient) -> None:
        with patch.object(client._legacy_client, "get", AsyncMock(return_value=MagicMock(
            status_code=200,
            text="",
        ))):
            items = await client.get_market_watch()
        assert items == []

    async def test_none_response(self, client: OptionTsetmcClient) -> None:
        with patch.object(client._legacy_client, "get", AsyncMock(return_value=MagicMock(
            status_code=404,
            text="",
        ))):
            items = await client.get_market_watch()
        assert items == []

    async def test_short_rows_skipped(self, client: OptionTsetmcClient) -> None:
        text = _build_market_watch_text(["a,b,c", "1,2,3,4,5"])
        with patch.object(client._legacy_client, "get", AsyncMock(return_value=MagicMock(
            status_code=200,
            text=text,
        ))):
            items = await client.get_market_watch()
        assert len(items) == 1
        assert items[0].ins_code == "1"


class TestGetBestLimits:
    async def test_parses_tsetmc_200_response_shape(self) -> None:
        payload = {
            "bestLimitsHistory": [
                {
                    "idn": 0,
                    "dEven": 0,
                    "hEven": 60127,
                    "refID": 15364957361,
                    "number": 4,
                    "qTitMeDem": 500,
                    "zOrdMeDem": 1,
                    "pMeDem": 9.0,
                    "pMeOf": 0.0,
                    "zOrdMeOf": 0,
                    "qTitMeOf": 0,
                    "title": None,
                    "insCode": None,
                }
            ]
        }
        client = OptionTsetmcClient(request_delay=0)
        client._request_json = AsyncMock(return_value=payload)  # type: ignore[method-assign]

        limits = await client.get_best_limits("11792961634816338", date(2026, 7, 29))

        assert len(limits) == 1
        assert limits[0].ref_id == 15364957361
        assert limits[0].depth_level == 4
        assert limits[0].bid_volume == 500

    async def test_valid_200_empty_history_is_explicitly_empty(self) -> None:
        client = OptionTsetmcClient(request_delay=0)
        client._request_json = AsyncMock(  # type: ignore[method-assign]
            return_value={"bestLimitsHistory": []}
        )

        limits = await client.get_best_limits("code", date(2026, 7, 30))

        assert limits == []

    async def test_unexpected_200_shape_is_an_error(self) -> None:
        client = OptionTsetmcClient(request_delay=0)
        client._request_json = AsyncMock(return_value={})  # type: ignore[method-assign]

        with pytest.raises(OptionTsetmcError, match="Unexpected BestLimits response"):
            await client.get_best_limits("code", date(2026, 7, 30))
