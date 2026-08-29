import asyncio
from datetime import date
from typing import Any

import httpx

from src.config import env, env_float, env_int

from src.collectors.stock.models import (
    BestLimitEntry,
    MarketWatchItem,
    StockInstrumentInfo,
    TradeEntry,
)

class StockTsetmcError(Exception):
    pass


class StockTsetmcClient:
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
        self._cdn_client: httpx.AsyncClient | None = None
        self._legacy_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "StockTsetmcClient":
        self._cdn_client = httpx.AsyncClient(
            base_url=env("TSETMC_CDN_BASE_URL"),
            headers={"User-Agent": env("TSETMC_USER_AGENT")},
            timeout=self._timeout,
        )
        self._legacy_client = httpx.AsyncClient(
            base_url=env("TSETMC_LEGACY_BASE_URL"),
            headers={"User-Agent": env("TSETMC_USER_AGENT")},
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def _request_json(self, path: str) -> dict[str, Any] | None:
        last_exc: Exception | None = None
        for attempt in range(self._retries):
            await asyncio.sleep(self._request_delay)
            async with self._semaphore:
                try:
                    assert self._cdn_client is not None
                    resp = await self._cdn_client.get(path)
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
        raise StockTsetmcError(f"Request failed after {self._retries} retries") from last_exc

    async def _request_text(self, path: str) -> str | None:
        last_exc: Exception | None = None
        for attempt in range(self._retries):
            await asyncio.sleep(self._request_delay)
            async with self._semaphore:
                try:
                    assert self._legacy_client is not None
                    resp = await self._legacy_client.get(path)
                except Exception as e:
                    last_exc = e
                    await asyncio.sleep(2**attempt)
                    continue
                if resp.status_code == 404:
                    return None
                if not resp.text.strip():
                    return None
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    last_exc = e
                    await asyncio.sleep(2**attempt)
                    continue
                return resp.text
        raise StockTsetmcError(f"Request failed after {self._retries} retries") from last_exc

    async def get_market_watch(self) -> list[MarketWatchItem]:
        raw = await self._request_text("/tsev2/data/MarketWatchInit.aspx?h=0&r=0")
        if raw is None:
            return []
        sections = raw.split("@")
        if len(sections) < 3:
            return []
        instrument_section = sections[2]
        items: list[MarketWatchItem] = []
        for row_str in instrument_section.split(";"):
            row_str = row_str.strip()
            if not row_str:
                continue
            fields = row_str.split(",")
            if len(fields) < 4:
                continue
            items.append(MarketWatchItem.from_row(fields))
        return items

    async def get_instrument_info(self, ins_code: str) -> StockInstrumentInfo | None:
        data = await self._request_json(f"/Instrument/GetInstrumentInfo/{ins_code}")
        if data is None:
            return None
        info = data.get("instrumentInfo")
        if info is None:
            return None
        return StockInstrumentInfo.from_dict(info)

    async def get_best_limits(
        self, ins_code: str, trade_date: date
    ) -> list[BestLimitEntry]:
        date_str = trade_date.strftime("%Y%m%d")
        data = await self._request_json(f"/BestLimits/{ins_code}/{date_str}")
        if data is None:
            return []
        raw_list = data.get("bestLimitsHistory") or []
        return [BestLimitEntry.from_dict(item) for item in raw_list]

    async def get_trade_history(
        self, ins_code: str, trade_date: date
    ) -> list[TradeEntry]:
        date_str = trade_date.strftime("%Y%m%d")
        data = await self._request_json(f"/Trade/GetTradeHistory/{ins_code}/{date_str}/false")
        if data is None:
            return []
        raw_list = data.get("tradeHistory") or []
        return [TradeEntry.from_dict(item) for item in raw_list]

    async def get_instrument_search(self, query: str) -> list[dict[str, Any]]:
        import urllib.parse
        encoded = urllib.parse.quote(query)
        data = await self._request_json(f"/Instrument/GetInstrumentSearch/{encoded}")
        if data is None:
            return []
        return data.get("instrumentSearch") or []

    async def close(self) -> None:
        if self._cdn_client is not None:
            await self._cdn_client.aclose()
            self._cdn_client = None
        if self._legacy_client is not None:
            await self._legacy_client.aclose()
            self._legacy_client = None
