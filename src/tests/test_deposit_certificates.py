from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.admin.gold.deposit_certificate_views import DepositCertificateOrderBookView, ParsianStreamSettingsView
from src.db.clickhouse.deposit_certificates import insert_order_books
from src.routes.deposit_certificates import latest_order_book, order_book_history, router


def request(authenticated=True):
    auth = SimpleNamespace(authenticate=AsyncMock(return_value=authenticated))
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(auth_backend=auth)), session={"user": "admin"})


def row():
    result = {
        "event_id": "a" * 64, "book_hash": "b" * 64, "contract_id": 41, "symbol": "GOLDBAR",
        "provider_event_at": datetime.fromisoformat("2026-09-05T10:00:00+03:30"),
        "received_at": datetime.fromisoformat("2026-09-05T10:00:01+03:30"), "redis_id": "1-0",
    }
    for side in ("bid", "ask"):
        for level in range(1, 4):
            result[f"{side}_price_{level}"] = level * 100
            result[f"{side}_volume_{level}"] = level * 10
    return result


@pytest.mark.asyncio
async def test_routes_are_authenticated_and_shape_levels():
    with pytest.raises(HTTPException) as exc:
        await latest_order_book(request(False), None)
    assert exc.value.status_code == 401
    with patch("src.routes.deposit_certificates.latest", AsyncMock(return_value=[row()])):
        result = await latest_order_book(request(), "GOLDBAR")
    assert result[0].bids[0].price == 100
    assert result[0].asks[2].volume == 30


@pytest.mark.asyncio
async def test_history_requires_timezone_and_ordered_range():
    naive = datetime(2026, 9, 5)
    with pytest.raises(HTTPException, match="timezone"):
        await order_book_history(request(), "GOLDBAR", naive, naive, 100)
    start = datetime.fromisoformat("2026-09-06T00:00:00+03:30")
    end = datetime.fromisoformat("2026-09-05T00:00:00+03:30")
    with pytest.raises(HTTPException, match="after"):
        await order_book_history(request(), "GOLDBAR", start, end, 100)


def test_insert_uses_explicit_clickhouse_columns():
    client = MagicMock()
    insert_order_books([row()], client)
    assert client.insert.call_args.args[0] == "deposit_certificate_order_book_stream"
    assert len(client.insert.call_args.kwargs["column_names"]) == 19


def test_migration_and_admin_contracts():
    source = Path("src/db/clickhouse/migrations/versions/022_deposit_certificate_stream.py").read_text()
    assert "ReplacingMergeTree" in source
    assert "INTERVAL 90 DAY DELETE" in source
    assert {route.path for route in router.routes} == {
        "/api/v1/deposit-certificates/order-book/latest",
        "/api/v1/deposit-certificates/order-book/history",
        "/api/v1/deposit-certificates/stream/status",
    }
    assert DepositCertificateOrderBookView.category == "Gold Market"
    assert ParsianStreamSettingsView.category == "Operations"
