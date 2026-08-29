import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from src.collectors.gold.models import (
    BestLimitEntry,
    GoldInstrumentInfo,
    MarketWatchItem,
    TradeEntry,
)
from src.db.clickhouse import price_to_storage


GOLD_ETF_SYMBOLS = {
    "طلا",
    "عیار",
    "گوهر",
    "کهربا",
    "زر",
    "زرفام",
    "ناب",
    "زرفشان",
    "جواهر",
    "تابش",
    "آلتون",
    "نفیس",
    "آتش",
    "گنج",
    "خزان",
}


def _normalize(text: str | None) -> str:
    if text is None:
        return ""
    return text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").strip()


def _convert_html_cell(html_str: str) -> str:
    import html as html_lib

    plain = re.sub(r"<br\s*/?>", " ", html_str, flags=re.I)
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = html_lib.unescape(plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    return _normalize(plain)


def parse_ime_funds_html(html: str) -> list[dict[str, str]]:
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    funds: list[dict[str, str]] = []
    seen: set[str] = set()

    for row in rows:
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 3:
            continue
        fund_type = _convert_html_cell(cells[0])
        if fund_type != "طلا" and "شاخه طلا" not in fund_type:
            continue

        symbol = _convert_html_cell(cells[1])
        link_cell = cells[2]
        match = re.search(r"(?:instInfo/|[?&]i=)(\d+)", link_cell, re.IGNORECASE)
        if not match:
            continue
        ins_code = match.group(1)
        if ins_code in seen:
            continue
        seen.add(ins_code)
        funds.append({"symbol": symbol, "ins_code": ins_code})
    return funds


def is_gold(item: MarketWatchItem) -> bool:
    norm_symbol = _normalize(item.symbol)
    norm_name = _normalize(item.name)

    # Ignore certificates (گواهی سپرده / سکه / شمش)
    if "گواهی" in norm_name or "گواهی" in norm_symbol:
        return False
    if norm_symbol.startswith("سکه") or norm_symbol.startswith("شمش"):
        return False

    # Match Gold Funds (صندوق‌های طلا)
    if norm_symbol in GOLD_ETF_SYMBOLS:
        return True
    if "صندوق" in norm_name and "طلا" in norm_name:
        return True
    if "طلا" in norm_symbol:
        return True
    return False


def market_watch_to_pg_attrs(item: MarketWatchItem) -> dict[str, Any]:
    return {
        "instrument_code": item.ins_code,
        "name_fa": item.name,
        "name_en": item.name,
        "symbol": item.symbol,
        "instrument_id": item.instrument_id,
        "status": "active",
    }


def search_item_to_pg_attrs(
    ins_code: str,
    name_fa: str | None,
    symbol: str | None,
    flow: int | None,
    flow_title: str | None,
    cgr_val_cot: str | None,
    cgr_val_cot_title: str | None,
    last_date: int | None,
) -> dict[str, Any]:
    return {
        "instrument_code": ins_code,
        "name_fa": name_fa,
        "symbol": symbol,
        "market_code": flow,
        "market_name": flow_title,
        "segment_code": cgr_val_cot,
        "segment_name": cgr_val_cot_title,
        "status": "active" if last_date == 1 else "expired",
    }


def instrument_info_to_pg_attrs(
    info: GoldInstrumentInfo,
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
        "maturity_date": _parse_maturity_date(info.name_en or info.symbol),
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


def _parse_maturity_date(name: str | None) -> date | None:
    if name is None:
        return None
    # Matches YYMMDD at the end of the symbol/code for certificates (e.g. 031201)
    match = re.search(r"(\d{6})$", name)
    if not match:
        return None
    raw = match.group(1)
    try:
        y, m, d = int(raw[:2]), int(raw[2:4]), int(raw[4:6])
        return date(2000 + y, m, d)
    except ValueError:
        return None


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
