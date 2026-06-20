import asyncio
from datetime import date
from typing import Any

import httpx

from src.collectors.bond.models import BestLimitEntry, BondInstrumentInfo, BondSearchItem, TradeEntry

BASE_URL = "https://cdn.tsetmc.com/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


class TsetmcError(Exception):
    pass


class TsetmcClient:
    def __init__(
        self,
        concurrency: int = 5,
        retries: int = 3,
        timeout: float = 30.0,
        request_delay: float = 0.5,
    ) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._retries = retries
        self._timeout = timeout
        self._request_delay = request_delay
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "TsetmcClient":
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=HEADERS,
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

    async def search_instruments(self, keyword: str = "اخزا") -> list[BondSearchItem]:
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
        data = await self._request(f"/Trade/GetTradeHistory/{ins_code}/{date_str}/true")
        if data is None:
            return []
        raw_list = data.get("tradeHistory") or []
        return [TradeEntry.from_dict(item) for item in raw_list]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
