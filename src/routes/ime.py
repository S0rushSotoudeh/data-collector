from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select
from starlette.requests import Request

from src.db.clickhouse.ime import get_ime_price_volume_points
from src.db.models.ime import ImeProducer, ImeProduct
from src.db.session import SessionLocal
from src.routes.admin_tasks import _require_admin


router = APIRouter(prefix="/admin/api/ime", tags=["admin-ime"])


@router.get("/products")
async def api_ime_products(request: Request, producer_code: int = Query(..., gt=0)):
    await _require_admin(request)
    with SessionLocal() as session:
        producer = session.get(ImeProducer, producer_code)
        if producer is None or not producer.enabled:
            raise HTTPException(status_code=404, detail="enabled producer not found")
        products = list(
            session.execute(
                select(ImeProduct)
                .where(ImeProduct.producer_code == producer_code)
                .order_by(ImeProduct.goods_name, ImeProduct.symbol)
            ).scalars()
        )
    return {
        "producer_code": producer_code,
        "products": [
            {
                "symbol": product.symbol,
                "goods_name": product.goods_name,
                "unit": product.unit,
                "currency": product.currency,
                "last_trade_date": product.last_trade_date,
            }
            for product in products
        ],
    }


@router.get("/price-volume")
async def api_ime_price_volume(
    request: Request,
    producer_code: int = Query(..., gt=0),
    symbol: str = Query(..., min_length=1, max_length=120),
    frm: date = Query(..., alias="from"),
    to: date = Query(...),
):
    await _require_admin(request)
    if frm > to:
        raise HTTPException(status_code=422, detail="from must not be after to")
    with SessionLocal() as session:
        producer = session.get(ImeProducer, producer_code)
        product = session.get(ImeProduct, (producer_code, symbol))
        if producer is None or not producer.enabled:
            raise HTTPException(status_code=404, detail="enabled producer not found")
        if product is None:
            raise HTTPException(status_code=404, detail="product not found for producer")
    rows = await get_ime_price_volume_points(producer_code, symbol, frm, to)
    points = []
    for row in rows:
        raw_price = float(row["price_thousand_rial"])
        points.append(
            {
                "trade_date": row["trade_date"].isoformat(),
                "jalali_date": row["jalali_date"],
                "offer_id": row["offer_id"],
                "source_trade_pk": row["source_trade_pk"],
                "contract_type": row["contract_type"],
                "price_thousand_rial": raw_price,
                "price_toman": raw_price * 100,
                "quantity": float(row["quantity"]),
                "unit": row["unit"],
            }
        )
    return {
        "producer_code": producer_code,
        "symbol": symbol,
        "goods_name": product.goods_name,
        "from": frm.isoformat(),
        "to": to.isoformat(),
        "points": points,
    }
