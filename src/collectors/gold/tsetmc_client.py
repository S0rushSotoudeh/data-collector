import asyncio
from datetime import date
from typing import Any

import httpx

from src.collectors.bond.models import BestLimitEntry, BondInstrumentInfo, BondSearchItem, TradeEntry
from src.config import env, env_float, env_int

class TsetmcError(Exception):
    pass


class TsetmcClient:
    def __init__(
        self,
        concurrency: int | None = None,
        retries: int | None = None,
        timeout: float | None = None,
        request_delay: float | None = None,
    ) -> None:
        self._semaphore = asyncio.Semaphore(
            concurrency if concurrency is not None else env_int("TSETMC_CONCURRENCY")
        )
        self._retries = retries if retries is not None else env_int("TSETMC_RETRIES")
        self._timeout = timeout if timeout is not None else env_float("TSETMC_TIMEOUT")
        self._request_delay = (
            request_delay
            if request_delay is not None
            else env_float("TSETMC_REQUEST_DELAY")
        )
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "TsetmcClient":
        self._client = httpx.AsyncClient(
            base_url=env("TSETMC_CDN_BASE_URL"),
            headers={"User-Agent": env("TSETMC_USER_AGENT")},
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, path: str) -> dict[str, Any] | None:
        last_exc: Exception | None = None
        for attempt in range(self._retries):
            await asyncio.sleep(self._request_delay)
            async with self._semaphore:
                try:
                    assert self._client is not None
                    resp = await self._client.get(path)
                except Exception as e:
                    last_exc = e
                    await asyncio.sleep(2**attempt)
                    continue
                if resp.status_code == 404:
                    return None
                ct = resp.headers.get("content-type", "")
                if "text/html" in ct or not resp.text.strip():
                    return None
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    last_exc = e
                    await asyncio.sleep(2**attempt)
                    continue
                return resp.json()
        raise TsetmcError(f"Request failed after {self._retries} retries") from last_exc

    async def search_instruments(self, keyword: str = "") -> list[BondSearchItem]:
        import urllib.parse
        encoded = urllib.parse.quote(keyword)
        data = await self._request(f"/Instrument/GetInstrumentSearch/{encoded}")
        if data is None:
            return []
        raw_list = data.get("instrumentSearch") or []
        return [BondSearchItem.from_dict(item) for item in raw_list]

    async def get_instrument_info(self, ins_code: str) -> BondInstrumentInfo | None:
        data = await self._request(f"/Instrument/GetInstrumentInfo/{ins_code}")
        if data is None:
            return None
        info = data.get("instrumentInfo")
        if info is None:
            return None
        return BondInstrumentInfo.from_dict(info)

    async def get_best_limits(
        self, ins_code: str, trade_date: date
    ) -> list[BestLimitEntry]:
        date_str = trade_date.strftime("%Y%m%d")
        data = await self._request(f"/BestLimits/{ins_code}/{date_str}")
        if data is None:
            return []
        raw_list = data.get("bestLimitsHistory") or []
        return [BestLimitEntry.from_dict(item) for item in raw_list]

    async def get_trade_history(
        self, ins_code: str, trade_date: date
    ) -> list[TradeEntry]:
        date_str = trade_date.strftime("%Y%m%d")
        data = await self._request(f"/Trade/GetTradeHistory/{ins_code}/{date_str}/false")
        if data is None:
            return []
        raw_list = data.get("tradeHistory") or []
        return [TradeEntry.from_dict(item) for item in raw_list]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
