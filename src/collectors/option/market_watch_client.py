import asyncio
from datetime import date
from typing import Any

import httpx

from src.collectors.option.models import (
    BestLimitEntry,
    MarketWatchItem,
    OptionInstrumentInfo,
    TradeEntry,
)

CDN_BASE_URL = "https://cdn.tsetmc.com/api"
LEGACY_BASE_URL = "https://old.tsetmc.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


class OptionTsetmcError(Exception):
    pass


class OptionTsetmcClient:
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
        self._cdn_client: httpx.AsyncClient | None = None
        self._legacy_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "OptionTsetmcClient":
        self._cdn_client = httpx.AsyncClient(
            base_url=CDN_BASE_URL,
            headers=HEADERS,
            timeout=self._timeout,
        )
        self._legacy_client = httpx.AsyncClient(
            base_url=LEGACY_BASE_URL,
            headers=HEADERS,
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
        raise OptionTsetmcError(f"Request failed after {self._retries} retries") from last_exc

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
        raise OptionTsetmcError(f"Request failed after {self._retries} retries") from last_exc

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

    async def get_instrument_info(self, ins_code: str) -> OptionInstrumentInfo | None:
        data = await self._request_json(f"/Instrument/GetInstrumentInfo/{ins_code}")
        if data is None:
            return None
        info = data.get("instrumentInfo")
        if info is None:
            return None
        return OptionInstrumentInfo.from_dict(info)

    async def get_best_limits(
        self, ins_code: str, trade_date: date
    ) -> list[BestLimitEntry]:
        date_str = trade_date.strftime("%Y%m%d")
        data = await self._request_json(f"/BestLimits/{ins_code}/{date_str}")
        if data is None:
            return []
        if not isinstance(data, dict) or "bestLimitsHistory" not in data:
            raise OptionTsetmcError(
                f"Unexpected BestLimits response for {ins_code}@{date_str}"
            )
        raw_list = data["bestLimitsHistory"]
        if raw_list is None:
            return []
        if not isinstance(raw_list, list):
            raise OptionTsetmcError(
                f"Invalid bestLimitsHistory for {ins_code}@{date_str}"
            )
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

    async def close(self) -> None:
        if self._cdn_client is not None:
            await self._cdn_client.aclose()
            self._cdn_client = None
        if self._legacy_client is not None:
            await self._legacy_client.aclose()
            self._legacy_client = None
