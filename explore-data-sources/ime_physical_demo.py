"""Read-only demo for Iran Mercantile Exchange physical-market trades.

Run inside the API container, for example:

    python /app/explore-data-sources/ime_physical_demo.py \
        --producer "سیمان مازندران" \
        --from-date 1402/01/01 \
        --to-date 1405/05/27
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx


BASE_URL = "https://www.ime.co.ir"
SERVICE_URL = "/subsystems/ime/services/home/imedata.asmx"
DEFAULT_PRODUCER = "سیمان مازندران"


class ImeDemoError(RuntimeError):
    """Raised when the IME demo cannot fetch or understand a response."""


@dataclass(frozen=True)
class DailyWeightedPrice:
    trade_date: str
    goods_name: str
    symbol: str
    quantity: Decimal
    weighted_price: Decimal
    unit: str
    currency: str
    trade_rows: int


def _decode_asmx_response(response: httpx.Response) -> Any:
    response.raise_for_status()
    data: Any = response.json()
    if not isinstance(data, dict) or "d" not in data:
        raise ImeDemoError("IME response does not contain the expected 'd' field")

    data = data["d"]
    while isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ImeDemoError("IME returned an invalid nested JSON payload") from exc
    return data


def _post(client: httpx.Client, method: str, payload: dict[str, Any]) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = client.post(f"{SERVICE_URL}/{method}", json=payload)
            return _decode_asmx_response(response)
        except (httpx.HTTPError, ImeDemoError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2**attempt)
    raise ImeDemoError(f"IME request {method!r} failed after 3 attempts") from last_error


def _normalise_name(value: str) -> str:
    return " ".join(value.replace("\u200c", " ").split()).casefold()


def resolve_producer(client: httpx.Client, producer_name: str) -> tuple[int, str]:
    producers = _post(client, "GetProducers", {"Language": 8})
    if not isinstance(producers, list):
        raise ImeDemoError("IME producer response is not a list")

    wanted = _normalise_name(producer_name)
    exact = [item for item in producers if _normalise_name(str(item.get("name", ""))) == wanted]
    if len(exact) == 1:
        return int(exact[0]["code"]), str(exact[0]["name"])

    partial = [
        str(item.get("name", ""))
        for item in producers
        if wanted in _normalise_name(str(item.get("name", "")))
    ]
    hint = f" Similar names: {', '.join(partial[:10])}" if partial else ""
    raise ImeDemoError(f"Producer {producer_name!r} was not found.{hint}")


def fetch_trades(
    client: httpx.Client,
    producer_code: int,
    from_date: str,
    to_date: str,
) -> list[dict[str, Any]]:
    rows = _post(
        client,
        "GetAmareMoamelatList",
        {
            "Language": 8,
            "fari": False,
            "GregorianFromDate": from_date,
            "GregorianToDate": to_date,
            "MainCat": 1,
            "Cat": 0,
            "SubCat": 0,
            "Producer": producer_code,
        },
    )
    if not isinstance(rows, list):
        raise ImeDemoError("IME trades response is not a list")
    return rows


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except InvalidOperation as exc:
        raise ImeDemoError(f"Unexpected numeric value from IME: {value!r}") from exc


def aggregate_daily_prices(rows: list[dict[str, Any]]) -> list[DailyWeightedPrice]:
    totals: dict[tuple[str, str, str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"quantity": Decimal(0), "total_price": Decimal(0), "rows": 0}
    )

    for row in rows:
        key = (
            str(row.get("date") or ""),
            str(row.get("GoodsName") or "").strip(),
            str(row.get("Symbol") or "").strip(),
            str(row.get("Unit") or "").strip(),
            str(row.get("Currency") or "").strip(),
        )
        quantity = _decimal(row.get("Quantity"))
        if quantity <= 0:
            continue
        totals[key]["quantity"] += quantity
        totals[key]["total_price"] += _decimal(row.get("TotalPrice"))
        totals[key]["rows"] += 1

    result = []
    for (trade_date, goods_name, symbol, unit, currency), values in totals.items():
        quantity = values["quantity"]
        result.append(
            DailyWeightedPrice(
                trade_date=trade_date,
                goods_name=goods_name,
                symbol=symbol,
                quantity=quantity,
                weighted_price=values["total_price"] / quantity,
                unit=unit,
                currency=currency,
                trade_rows=values["rows"],
            )
        )
    return sorted(result, key=lambda item: (item.trade_date, item.goods_name, item.symbol))


def print_result(
    producer_name: str,
    producer_code: int,
    raw_rows: list[dict[str, Any]],
    daily_prices: list[DailyWeightedPrice],
    limit: int,
) -> None:
    dates = sorted({str(row.get("date")) for row in raw_rows if row.get("date")})
    products = {str(row.get("Symbol")) for row in raw_rows if row.get("Symbol")}
    print(f"producer      : {producer_name} (code={producer_code})")
    print(f"raw rows      : {len(raw_rows):,}")
    print(f"date coverage : {dates[0] if dates else '-'} .. {dates[-1] if dates else '-'}")
    print(f"products      : {len(products):,}")
    print(f"daily points  : {len(daily_prices):,}")
    print("price unit    : thousand rials per traded unit (TotalPrice / Quantity)")
    print()
    print("date       | symbol                    | weighted price | quantity | product")
    print("-" * 120)

    selected = daily_prices if limit == 0 else daily_prices[-limit:]
    for item in selected:
        price = f"{item.weighted_price:,.2f}"
        quantity = f"{item.quantity:,.2f}"
        print(
            f"{item.trade_date:<10} | {item.symbol:<25} | {price:>14} | "
            f"{quantity:>10} {item.unit:<4} | {item.goods_name}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch and aggregate IME physical trades for one selected producer."
    )
    parser.add_argument("--producer", default=DEFAULT_PRODUCER)
    parser.add_argument("--from-date", default="1402/01/01", help="Jalali YYYY/MM/DD")
    parser.add_argument("--to-date", default="1405/05/27", help="Jalali YYYY/MM/DD")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of latest daily product points to print; 0 prints all.",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    if args.limit < 0:
        raise ImeDemoError("--limit cannot be negative")

    headers = {
        "Accept": "text/plain, */*; q=0.01",
        "Referer": f"{BASE_URL}/offer-stat.html",
        "User-Agent": "data-collector-ime-readonly-demo/0.1",
        "X-Requested-With": "XMLHttpRequest",
    }
    with httpx.Client(
        base_url=BASE_URL,
        headers=headers,
        follow_redirects=True,
        timeout=60,
    ) as client:
        producer_code, canonical_name = resolve_producer(client, args.producer)
        rows = fetch_trades(client, producer_code, args.from_date, args.to_date)

    daily_prices = aggregate_daily_prices(rows)
    print_result(canonical_name, producer_code, rows, daily_prices, args.limit)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ImeDemoError, httpx.HTTPError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
