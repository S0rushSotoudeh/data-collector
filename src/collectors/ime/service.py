from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

import jdatetime
from sqlalchemy import select

from src.collectors.ime.client import ImeClient
from src.db.clickhouse.ime import insert_ime_physical_trades
from src.db.models.ime import ImeProducer, ImeProduct
from src.db.session import SessionLocal


ALL_HISTORY_START = date(2001, 3, 21)  # 1380/01/01


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except InvalidOperation as exc:
        raise ValueError(f"Unexpected IME numeric value: {value!r}") from exc


def _jalali_to_gregorian(value: Any) -> date | None:
    if not value:
        return None
    try:
        year, month, day = (int(part) for part in str(value).split("/")[:3])
        return jdatetime.date(year, month, day).togregorian()
    except (TypeError, ValueError):
        return None


def transform_trade(raw: dict[str, Any], producer_code: int) -> dict[str, Any] | None:
    price = raw.get("Price")
    quantity = _decimal(raw.get("Quantity"))
    trade_date = _jalali_to_gregorian(raw.get("date"))
    if price is None or quantity <= 0 or trade_date is None:
        return None
    return {
        "producer_code": producer_code,
        "producer_name": str(raw.get("ProducerName") or "").strip(),
        "product_symbol": str(raw.get("Symbol") or "").strip(),
        "product_name": str(raw.get("GoodsName") or "").strip(),
        "trade_date": trade_date,
        "jalali_date": str(raw.get("date") or ""),
        "delivery_date": _jalali_to_gregorian(raw.get("DeliveryDate")),
        "offer_id": str(raw.get("arzehPk") or ""),
        "source_trade_pk": int(raw.get("xTalarReportPK") or 0),
        "contract_type": str(raw.get("ContractType") or "").strip(),
        "price_thousand_rial": _decimal(price),
        "quantity": quantity,
        "total_value_thousand_rial": _decimal(raw.get("TotalPrice")),
        "unit": str(raw.get("Unit") or "").strip(),
        "currency": str(raw.get("Currency") or "").strip(),
        "hall": str(raw.get("Talar") or "").strip(),
        "warehouse": str(raw.get("Warehouse") or "").strip(),
        "packet_name": str(raw.get("PacketName") or "").strip(),
        "settlement_type": str(raw.get("Tasvieh") or "").strip(),
        "category": str(raw.get("Category") or "").strip(),
        "raw_json": json.dumps(raw, ensure_ascii=False, separators=(",", ":")),
        "ingested_at": datetime.now(timezone.utc),
    }


async def sync_producers(progress=None) -> dict[str, Any]:
    async with ImeClient() as client:
        rows = await client.get_producers()
    now = datetime.now(timezone.utc)
    synced = 0
    if progress:
        progress.set_total(len(rows))
    with SessionLocal() as session:
        for raw in rows:
            code = int(raw.get("code") or 0)
            name = str(raw.get("name") or "").strip()
            if not code or not name:
                if progress:
                    progress.advance(warning_count=1)
                continue
            item = session.get(ImeProducer, code)
            if item is None:
                item = ImeProducer(producer_code=code, name=name, enabled=(code == 5219))
            else:
                item.name = name
            item.synced_at = now
            session.add(item)
            synced += 1
            if progress:
                progress.advance(output_count=1)
        session.commit()
    return {"synced": synced, "producer_count": len(rows)}


def enabled_producer_codes() -> list[int]:
    with SessionLocal() as session:
        return list(
            session.execute(
                select(ImeProducer.producer_code)
                .where(ImeProducer.enabled.is_(True))
                .order_by(ImeProducer.producer_code)
            ).scalars()
        )


def _chunks(start_date: date, end_date: date) -> list[tuple[date, date]]:
    size = max(1, int(os.environ.get("IME_BACKFILL_CHUNK_DAYS", "365")))
    chunks: list[tuple[date, date]] = []
    current = start_date
    while current <= end_date:
        chunk_end = min(end_date, current + timedelta(days=size - 1))
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def _upsert_products(producer_code: int, rows: Iterable[dict[str, Any]]) -> None:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = row["product_symbol"]
        previous = latest.get(symbol)
        if previous is None or row["trade_date"] >= previous["trade_date"]:
            latest[symbol] = row
    with SessionLocal() as session:
        for symbol, row in latest.items():
            product = session.get(ImeProduct, (producer_code, symbol))
            if product is None:
                product = ImeProduct(
                    producer_code=producer_code, symbol=symbol, goods_name=row["product_name"]
                )
            elif product.last_trade_date is not None and row["trade_date"] < product.last_trade_date:
                continue
            product.goods_name = row["product_name"]
            product.unit = row["unit"]
            product.currency = row["currency"]
            product.category = row["category"] or None
            product.last_trade_date = row["trade_date"]
            session.add(product)
        session.commit()


async def collect_trades(
    producer_codes: list[int], start_date: date, end_date: date, progress=None
) -> dict[str, Any]:
    jobs = [(code, start, end) for code in producer_codes for start, end in _chunks(start_date, end_date)]
    if progress:
        progress.set_total(len(jobs))
    inserted = 0
    warnings = 0
    products: set[tuple[int, str]] = set()
    first_trade_date: date | None = None
    last_trade_date: date | None = None
    async with ImeClient() as client:
        for code, chunk_start, chunk_end in jobs:
            raw_rows = await client.get_physical_trades(code, chunk_start, chunk_end)
            transformed = [item for raw in raw_rows if (item := transform_trade(raw, code)) is not None]
            skipped = len(raw_rows) - len(transformed)
            insert_ime_physical_trades(transformed)
            _upsert_products(code, transformed)
            inserted += len(transformed)
            warnings += skipped
            for row in transformed:
                products.add((code, row["product_symbol"]))
                first_trade_date = min(first_trade_date, row["trade_date"]) if first_trade_date else row["trade_date"]
                last_trade_date = max(last_trade_date, row["trade_date"]) if last_trade_date else row["trade_date"]
            if progress:
                progress.advance(output_count=len(transformed), warning_count=skipped)
    return {
        "inserted": inserted,
        "warning_count": warnings,
        "producer_count": len(producer_codes),
        "product_count": len(products),
        "chunk_count": len(jobs),
        "first_trade_date": first_trade_date,
        "last_trade_date": last_trade_date,
    }
