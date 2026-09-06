from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from starlette.requests import Request

from src.collectors.parsian_stream import stream_status
from src.db.clickhouse.deposit_certificates import history, latest
from src.routes.admin_tasks import _require_admin

Symbol = Literal["GOLDBAR", "GOLDCOIN"]
router = APIRouter(prefix="/api/v1/deposit-certificates", tags=["deposit-certificates"])


class Level(BaseModel):
    level: int
    price: int
    volume: int


class OrderBook(BaseModel):
    event_id: str
    contract_id: int
    symbol: Symbol
    provider_event_at: datetime
    received_at: datetime
    bids: list[Level]
    asks: list[Level]


def _response(row: dict) -> OrderBook:
    def levels(side: str) -> list[Level]:
        return [Level(level=n, price=row[f"{side}_price_{n}"], volume=row[f"{side}_volume_{n}"]) for n in range(1, 4)]
    return OrderBook(
        event_id=row["event_id"], contract_id=row["contract_id"], symbol=row["symbol"],
        provider_event_at=row["provider_event_at"], received_at=row["received_at"],
        bids=levels("bid"), asks=levels("ask"),
    )


@router.get("/order-book/latest", response_model=list[OrderBook])
async def latest_order_book(request: Request, symbol: Symbol | None = None):
    await _require_admin(request)
    return [_response(row) for row in await latest(symbol)]


@router.get("/order-book/history", response_model=list[OrderBook])
async def order_book_history(
    request: Request,
    symbol: Symbol,
    start: datetime = Query(..., alias="from"),
    end: datetime = Query(..., alias="to"),
    limit: int = Query(1000, ge=1, le=10_000),
):
    await _require_admin(request)
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(status_code=422, detail="from and to must include a timezone")
    if start > end:
        raise HTTPException(status_code=422, detail="from must not be after to")
    return [_response(row) for row in await history(symbol, start, end, limit)]


@router.get("/stream/status")
async def deposit_certificate_stream_status(request: Request):
    await _require_admin(request)
    return await stream_status()
