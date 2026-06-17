from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.collectors.bond.tsetmc_client import TsetmcClient


class TestTsetmcClient:
    @pytest.fixture
    async def client(self) -> TsetmcClient:
        async with TsetmcClient(concurrency=10, retries=3, timeout=5) as c:
            yield c

    async def test_search_instruments_success(
        self, client: TsetmcClient
    ) -> None:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.text = '{"instrumentSearch": [{"insCode": "123", "lastDate": 1}]}'
        mock_resp.json.return_value = {
            "instrumentSearch": [{"insCode": "123", "lastDate": 1}]
        }

        with patch.object(client._client, "get", AsyncMock(return_value=mock_resp)):
            results = await client.search_instruments("اخزا")
        assert len(results) == 1
        assert results[0].ins_code == "123"
        assert results[0].last_date == 1

    async def test_search_instruments_empty(
        self, client: TsetmcClient
    ) -> None:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.text = '{"instrumentSearch": []}'
        mock_resp.json.return_value = {"instrumentSearch": []}

        with patch.object(client._client, "get", AsyncMock(return_value=mock_resp)):
            results = await client.search_instruments("اخزا")
        assert results == []

    async def test_html_response_returns_empty(
        self, client: TsetmcClient
    ) -> None:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = "<html>...</html>"
        mock_resp.json.side_effect = ValueError

        with patch.object(client._client, "get", AsyncMock(return_value=mock_resp)):
            result = await client.get_best_limits("123", date(2026, 6, 10))
        assert result == []

    async def test_empty_body_returns_empty(
        self, client: TsetmcClient
    ) -> None:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.text = ""

        with patch.object(client._client, "get", AsyncMock(return_value=mock_resp)):
            result = await client.get_best_limits("123", date(2026, 6, 10))
        assert result == []

    async def test_404_returns_empty(
        self, client: TsetmcClient
    ) -> None:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 404
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.text = "{}"
        mock_resp.is_error = True

        with patch.object(client._client, "get", AsyncMock(return_value=mock_resp)):
            result = await client.get_best_limits("123", date(2026, 6, 10))
        assert result == []

    async def test_retry_on_5xx_then_succeeds(
        self, client: TsetmcClient
    ) -> None:
        fail_resp = MagicMock(spec=httpx.Response)
        fail_resp.status_code = 500
        fail_resp.headers = {"content-type": "application/json"}
        fail_resp.text = "{}"
        fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=fail_resp
        )

        ok_resp = MagicMock(spec=httpx.Response)
        ok_resp.status_code = 200
        ok_resp.headers = {"content-type": "application/json"}
        ok_resp.text = '{"instrumentInfo": {"insCode": "123"}}'
        ok_resp.json.return_value = {"instrumentInfo": {"insCode": "123"}}

        mock_get = AsyncMock(side_effect=[fail_resp, ok_resp])
        with patch.object(client._client, "get", mock_get):
            result = await client.get_instrument_info("123")
        assert result is not None
        assert result.ins_code == "123"
        assert mock_get.call_count == 2

    async def test_get_instrument_info_none(
        self, client: TsetmcClient
    ) -> None:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 404
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.text = "{}"

        with patch.object(client._client, "get", AsyncMock(return_value=mock_resp)):
            result = await client.get_instrument_info("123")
        assert result is None

    async def test_get_best_limits_success(
        self, client: TsetmcClient
    ) -> None:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.text = '{"bestLimitsHistory": [{"hEven": 60123, "number": 1}]}'
        mock_resp.json.return_value = {
            "bestLimitsHistory": [{"hEven": 60123, "number": 1}]
        }

        with patch.object(client._client, "get", AsyncMock(return_value=mock_resp)):
            results = await client.get_best_limits("123", date(2026, 6, 10))
        assert len(results) == 1
        assert results[0].h_even == 60123
        assert results[0].depth_level == 1