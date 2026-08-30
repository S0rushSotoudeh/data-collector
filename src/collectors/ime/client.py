from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import date
from html import unescape
from typing import Any

import httpx
import jdatetime

class ImeError(RuntimeError):
    pass


def parse_gold_etf_ins_codes(page: str) -> set[str]:
    codes: set[str] = set()
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", page, flags=re.IGNORECASE | re.DOTALL):
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.IGNORECASE | re.DOTALL)
        if len(cells) < 3:
            continue

        category = _html_text(cells[0])
        if category != "طلا" and "شاخه طلا" not in category:
            continue

        match = re.search(r"(?:instInfo/|[?&]i=)(\d+)", unescape(cells[2]), re.IGNORECASE)
        if match is None:
            raise ImeError("Official IME gold ETF row has no TSETMC InsCode")
        codes.add(match.group(1))

    if not codes:
        raise ImeError("Official IME page returned no gold ETFs")
    return codes


def _html_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    value = unescape(re.sub(r"<[^>]+>", " ", value))
    value = value.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    return " ".join(value.split())


def decode_asmx_response(response: httpx.Response) -> Any:
    response.raise_for_status()
    data: Any = response.json()
    if not isinstance(data, dict) or "d" not in data:
        raise ImeError("IME response does not contain the expected 'd' field")
    data = data["d"]
    while isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ImeError("IME returned invalid nested JSON") from exc
    return data


def to_jalali_string(value: date) -> str:
    converted = jdatetime.date.fromgregorian(date=value)
    return f"{converted.year:04d}/{converted.month:02d}/{converted.day:02d}"


class ImeClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        retries: int | None = None,
        request_delay: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url or os.environ.get("IME_BASE_URL", "https://www.ime.co.ir")
        self.timeout = timeout if timeout is not None else float(os.environ.get("IME_TIMEOUT", "60"))
        self.retries = retries if retries is not None else int(os.environ.get("IME_RETRIES", "3"))
        self.request_delay = (
            request_delay if request_delay is not None else float(os.environ.get("IME_REQUEST_DELAY", "0.5"))
        )
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "ImeClient":
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers={
                    "Accept": "text/plain, */*; q=0.01",
                    "Referer": f"{self.base_url}/offer-stat.html",
                    "User-Agent": os.environ.get(
                        "IME_USER_AGENT",
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    ),
                    "X-Requested-With": "XMLHttpRequest",
                },
                follow_redirects=True,
            )
        return self

    async def __aexit__(self, *_args: Any) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _post(self, method: str, payload: dict[str, Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            if self.request_delay:
                await asyncio.sleep(self.request_delay)
            try:
                assert self._client is not None
                response = await self._client.post(
                    f"/subsystems/ime/services/home/imedata.asmx/{method}", json=payload
                )
                return decode_asmx_response(response)
            except (httpx.HTTPError, ImeError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    await asyncio.sleep(2**attempt)
        raise ImeError(f"IME request {method!r} failed after {self.retries} attempts") from last_error

    async def _get_text(self, path: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            if self.request_delay:
                await asyncio.sleep(self.request_delay)
            try:
                assert self._client is not None
                response = await self._client.get(path)
                response.raise_for_status()
                return response.text
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    await asyncio.sleep(2**attempt)
        raise ImeError(f"IME request {path!r} failed after {self.retries} attempts") from last_error

    async def get_gold_etf_ins_codes(self) -> set[str]:
        return parse_gold_etf_ins_codes(await self._get_text("/ExchangeTradedFunds.html"))

    async def get_producers(self) -> list[dict[str, Any]]:
        data = await self._post("GetProducers", {"Language": 8})
        if not isinstance(data, list):
            raise ImeError("IME producer response is not a list")
        return data

    async def get_physical_trades(
        self, producer_code: int, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        data = await self._post(
            "GetAmareMoamelatList",
            {
                "Language": 8, "fari": False,
                "GregorianFromDate": to_jalali_string(start_date),
                "GregorianToDate": to_jalali_string(end_date),
                "MainCat": 1, "Cat": 0, "SubCat": 0, "Producer": producer_code,
            },
        )
        if not isinstance(data, list):
            raise ImeError("IME trades response is not a list")
        return data
