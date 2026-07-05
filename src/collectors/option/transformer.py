import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from src.collectors.option.models import (
    BestLimitEntry,
    MarketWatchItem,
    OptionInstrumentInfo,
    TradeEntry,
)
from src.db.clickhouse import price_to_storage

_OPTION_NAME_RE = re.compile(r"^(اختیار([خف]))\s+(\S+?)-(\d+)-(\d{4}/\d{2}/\d{2})$")
_TYPE_MAP = {"خ": "call", "ف": "put"}


def _normalize(name: str | None) -> str:
    if name is None:
        return ""
    return name.replace("ي", "ی")


def is_option(item: MarketWatchItem) -> bool:
    return "اختیار" in _normalize(item.name)


def parse_option_name(
    name: str | None,
) -> tuple[str | None, str | None, Decimal | None, date | None]:
    if not name:
        return None, None, None, None
    normalized = _normalize(name)
    m = _OPTION_NAME_RE.match(normalized)
    if not m:
        return None, None, None, None
    type_char = m.group(2)
    underlying = m.group(3)
    strike_str = m.group(4)
    expiry_str = m.group(5)
    opt_type = _TYPE_MAP.get(type_char)
    try:
        strike = Decimal(strike_str)
    except Exception:
        strike = None
    expiry = _jalali_to_date(expiry_str)
    return opt_type, underlying, strike, expiry


def _jalali_to_date(jalali_str: str) -> date | None:
    try:
        import jdatetime

        parts = jalali_str.split("/")
        if len(parts) != 3:
            return None
        return jdatetime.date(int(parts[0]), int(parts[1]), int(parts[2])).togregorian()
    except Exception:
        return None


def market_watch_to_pg_attrs(item: MarketWatchItem) -> dict[str, Any]:
    opt_type, underlying, strike, expiry = parse_option_name(item.name)
    return {
        "instrument_code": item.ins_code,
        "name_en": item.name,
        "symbol": item.symbol,
        "instrument_id": item.instrument_id,
        "option_type": opt_type,
        "underlying_symbol": underlying,
        "strike_price": strike,
        "expiry_date": expiry,
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
    info: OptionInstrumentInfo,
    status: str | None = None,
) -> dict[str, Any]:
    opt_type, underlying, strike, expiry = parse_option_name(info.name_fa)
    if opt_type is None and info.name_en:
        opt_type, underlying, strike, expiry = parse_option_name(info.name_en)

    attrs: dict[str, Any] = {
        "instrument_code": info.ins_code,
        "name_fa": info.name_fa,
        "name_en": info.name_en,
        "symbol": info.symbol,
        "isin": info.isin,
        "instrument_id": info.instrument_id,
        "total_issued": _safe_int(info.total_issued),
        "base_volume": info.base_volume,
        "option_type": opt_type,
        "underlying_symbol": underlying,
        "strike_price": _safe_decimal(strike),
        "expiry_date": expiry,
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
