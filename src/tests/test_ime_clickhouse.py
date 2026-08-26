from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.clickhouse.ime import (
    IME_PHYSICAL_TRADES_COLUMNS,
    IME_PHYSICAL_TRADES_DDL,
    get_ime_price_volume_points,
    insert_ime_physical_trades,
)


def test_ime_table_is_permanent_and_idempotent_by_contract() -> None:
    compact = " ".join(IME_PHYSICAL_TRADES_DDL.split())

    assert "ReplacingMergeTree(ingested_at)" in compact
    assert "ORDER BY (producer_code, trade_date, product_symbol, offer_id, contract_type, source_trade_pk)" in compact
    assert "TTL" not in compact


def test_insert_uses_raw_price_column_without_aggregation() -> None:
    client = MagicMock()
    row = {column: None for column in IME_PHYSICAL_TRADES_COLUMNS}
    row.update(
        {
            "producer_code": 5219,
            "trade_date": date(2026, 8, 18),
            "product_symbol": "MAS-CPCANG32.5-L50-00",
            "offer_id": "99123",
            "contract_type": "نقدی",
            "price_thousand_rial": Decimal("35740"),
            "quantity": Decimal("1050"),
        }
    )

    insert_ime_physical_trades([row], client)

    inserted = client.insert.call_args.args[1][0]
    assert inserted[IME_PHYSICAL_TRADES_COLUMNS.index("price_thousand_rial")] == Decimal("35740")
    assert client.insert.call_args.kwargs["column_names"] == IME_PHYSICAL_TRADES_COLUMNS


@pytest.mark.asyncio
async def test_price_volume_points_preserve_source_row_identity() -> None:
    client = AsyncMock()
    client.query.return_value.result_rows = [
        (
            date(2026, 8, 18),
            "1405/05/27",
            "99123",
            88123,
            "نقدی",
            Decimal("35740"),
            Decimal("1050"),
            "تن",
        )
    ]

    with patch("src.db.clickhouse.ime.get_async_client", return_value=client):
        points = await get_ime_price_volume_points(
            5219,
            "MAS-CPCANG32.5-L50-00",
            date(2026, 8, 18),
            date(2026, 8, 18),
        )

    assert points[0]["source_trade_pk"] == 88123
    assert points[0]["contract_type"] == "نقدی"
    assert points[0]["price_thousand_rial"] == Decimal("35740")
