from dataclasses import dataclass
from typing import Any


@dataclass
class MarketWatchItem:
    ins_code: str
    instrument_id: str
    symbol: str
    name: str
    flow_code: str

    @classmethod
    def from_row(cls, row: list[str]) -> "MarketWatchItem":
        def _get(idx: int) -> str:
            return row[idx] if idx < len(row) else ""

        return cls(
            ins_code=_get(0),
            instrument_id=_get(1),
            symbol=_get(2),
            name=_get(3),
            flow_code=_get(25),
        )


@dataclass
class GoldSearchItem:
    ins_code: str
    name_fa: str | None
    symbol: str | None
    flow: int | None
    flow_title: str | None
    cgr_val_cot: str | None
    cgr_val_cot_title: str | None
    last_date: int | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GoldSearchItem":
        return cls(
            ins_code=str(d.get("insCode", "")),
            name_fa=d.get("lVal30"),
            symbol=d.get("lVal18AFC"),
            flow=d.get("flow"),
            flow_title=d.get("flowTitle"),
            cgr_val_cot=d.get("cgrValCot"),
            cgr_val_cot_title=d.get("cgrValCotTitle"),
            last_date=d.get("lastDate"),
        )


@dataclass
class GoldInstrumentInfo:
    ins_code: str
    name_fa: str | None
    name_en: str | None
    symbol: str | None
    isin: str | None
    instrument_id: str | None
    total_issued: float | None
    base_volume: int | None
    flow: int | None
    flow_title: str | None
    cgr_val_cot: str | None
    cgr_val_cot_title: str | None
    c_sec_val: str | None
    l_sec_val: str | None
    price_ceiling: float | None
    price_floor: float | None
    min_week: float | None
    max_week: float | None
    min_year: float | None
    max_year: float | None
    avg_daily_volume_5y: float | None
    d_even: int | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GoldInstrumentInfo":
        static = d.get("staticThreshold", {})
        return cls(
            ins_code=str(d.get("insCode", "")),
            name_fa=d.get("lVal30"),
            name_en=d.get("lVal18"),
            symbol=d.get("lVal18AFC"),
            isin=d.get("cIsin"),
            instrument_id=d.get("instrumentID"),
            total_issued=d.get("zTitad"),
            base_volume=d.get("baseVol"),
            flow=d.get("flow"),
            flow_title=d.get("flowTitle"),
            cgr_val_cot=d.get("cgrValCot"),
            cgr_val_cot_title=d.get("cgrValCotTitle"),
            c_sec_val=d.get("cSecVal"),
            l_sec_val=d.get("lSecVal"),
            price_ceiling=static.get("psGelStaMax"),
            price_floor=static.get("psGelStaMin"),
            min_week=d.get("minWeek"),
            max_week=d.get("maxWeek"),
            min_year=d.get("minYear"),
            max_year=d.get("maxYear"),
            avg_daily_volume_5y=d.get("qTotTran5JAvg"),
            d_even=d.get("dEven"),
        )


@dataclass
class TradeEntry:
    h_even: int
    n_tran: int
    price: float
    volume: int
    canceled: bool

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TradeEntry":
        return cls(
            h_even=int(d.get("hEven", 0)),
            n_tran=int(d.get("nTran", 0)),
            price=float(d.get("pTran", 0.0)),
            volume=int(d.get("qTitTran", 0)),
            canceled=bool(d.get("canceled", False)),
        )


@dataclass
class BestLimitEntry:
    h_even: int
    ref_id: int
    depth_level: int
    bid_price: float
    bid_volume: int
    bid_order_count: int
    ask_price: float
    ask_volume: int
    ask_order_count: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BestLimitEntry":
        return cls(
            h_even=int(d.get("hEven", 0)),
            ref_id=int(d.get("refID", 0)),
            depth_level=int(d.get("number", 0)),
            bid_price=float(d.get("pMeDem", 0.0)),
            bid_volume=int(d.get("qTitMeDem", 0)),
            bid_order_count=int(d.get("zOrdMeDem", 0)),
            ask_price=float(d.get("pMeOf", 0.0)),
            ask_volume=int(d.get("qTitMeOf", 0)),
            ask_order_count=int(d.get("zOrdMeOf", 0)),
        )
