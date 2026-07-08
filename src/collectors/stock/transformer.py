from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from src.collectors.stock.models import (
    BestLimitEntry,
    MarketWatchItem,
    StockInstrumentInfo,
    TradeEntry,
)
from src.db.clickhouse import price_to_storage


def _normalize(name: str | None) -> str:
    if name is None:
        return ""
    return name.replace("ي", "ی")


def is_option(item: MarketWatchItem) -> bool:
    return "اختیار" in _normalize(item.name)


def is_bond(item: MarketWatchItem) -> bool:
    return "خزانه" in _normalize(item.name)


def is_stock(item: MarketWatchItem) -> bool:
    return not is_option(item) and not is_bond(item)


def market_watch_to_pg_attrs(item: MarketWatchItem) -> dict[str, Any]:
    return {
        "instrument_code": item.ins_code,
        "name_fa": item.name,
        "name_en": item.name,
        "symbol": item.symbol,
        "instrument_id": item.instrument_id,
        "status": "active",
    }


def trades_to_trade_rows(
    trades: list[TradeEntry],
    instrument_code: str,
    trade_date: date,
    data_source: str = "tsetmc",
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for entry in trades:
        price = price_to_storage(entry.price)
        result.append({
            "instrument_code": instrument_code,
            "trade_date": trade_date,
            "trade_time": entry.h_even,
            "trade_id": entry.n_tran,
            "price": price,
            "volume": entry.volume,
            "value": price * entry.volume,
            "is_canceled": 1 if entry.canceled else 0,
            "data_source": data_source,
            "ingested_at": now,
        })
    return result


def best_limits_to_order_book_rows(
    limits: list[BestLimitEntry],
    instrument_code: str,
    trade_date: date,
    data_source: str = "tsetmc",
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for entry in limits:
        result.append({
            "instrument_code": instrument_code,
            "trade_date": trade_date,
            "trade_time": entry.h_even,
            "ref_id": entry.ref_id,
            "depth_level": entry.depth_level,
            "bid_price": price_to_storage(entry.bid_price),
            "bid_volume": entry.bid_volume,
            "bid_order_count": entry.bid_order_count,
            "ask_price": price_to_storage(entry.ask_price),
            "ask_volume": entry.ask_volume,
            "ask_order_count": entry.ask_order_count,
            "data_source": data_source,
            "ingested_at": now,
        })
    return result


def instrument_info_to_pg_attrs(
    info: StockInstrumentInfo,
    status: str | None = None,
) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "instrument_code": info.ins_code,
        "name_fa": info.name_fa,
        "name_en": info.name_en,
        "symbol": info.symbol,
        "isin": info.isin,
        "instrument_id": info.instrument_id,
        "total_issued": _safe_int(info.total_issued),
        "base_volume": info.base_volume,
        "market_code": info.flow,
        "market_name": info.flow_title,
        "segment_code": info.cgr_val_cot,
        "segment_name": info.cgr_val_cot_title,
        "security_type_code": info.c_sec_val,
        "security_type_name": info.l_sec_val,
        "price_ceiling": _safe_decimal(info.price_ceiling),
        "price_floor": _safe_decimal(info.price_floor),
        "low_52w": _safe_decimal(info.min_week),
        "high_52w": _safe_decimal(info.max_week),
        "low_yearly": _safe_decimal(info.min_year),
        "high_yearly": _safe_decimal(info.max_year),
        "avg_daily_volume_5y": _safe_int(info.avg_daily_volume_5y),
        "last_trade_date": _d_even_to_date(info.d_even),
    }
    if status is not None:
        attrs["status"] = status
    return attrs


def _safe_decimal(value: float | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _safe_int(value: float | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _d_even_to_date(d_even: int | None) -> date | None:
    if d_even is None or d_even == 0:
        return None
    s = str(d_even)
    if len(s) != 8:
        return None
    return date(int(s[:4]), int(s[4:6]), int(s[6:]))
