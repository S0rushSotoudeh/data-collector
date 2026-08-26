from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.admin.ime.views import ImePriceVolumeView, ImeProducerAdmin, ImeProductAdmin, ImeTradesView
from src.collectors.ime.service import ALL_HISTORY_START
from src.routes.admin_tasks import ImeBackfillRequest, api_backfill_ime_physical_trades
from src.routes.ime import api_ime_price_volume, router as ime_router
from src.services.operation_runs import TASK_SPECS


def _request(*, authenticated: bool = True):
    auth = SimpleNamespace(authenticate=AsyncMock(return_value=authenticated))
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(auth_backend=auth)),
        session={"user": "admin"},
    )


def test_ime_routes_and_admin_page_contract() -> None:
    paths = {route.path for route in ime_router.routes}

    assert paths == {"/admin/api/ime/products", "/admin/api/ime/price-volume"}
    assert ImeProducerAdmin.form_columns == [ImeProducerAdmin.model.enabled]
    assert ImeProducerAdmin.can_create is False
    assert ImeProducerAdmin.can_delete is False
    assert ImeProductAdmin.can_create is False
    assert ImeProductAdmin.can_edit is False
    assert ImeProductAdmin.can_delete is False
    assert ImeTradesView.category == "IME Physical Market"
    assert ImePriceVolumeView.category == "IME Physical Market"


def test_ime_tasks_share_collection_run_family() -> None:
    for name in (
        "src.tasks.sync_ime_producers",
        "src.tasks.backfill_ime_physical_trades",
        "src.tasks.fetch_recent_ime_physical_trades",
    ):
        assert TASK_SPECS[name].family == "collection"


def test_ime_backfill_validation_and_all_history_contract() -> None:
    with pytest.raises(ValueError, match="required unless all_history"):
        ImeBackfillRequest(producer_code=5219)
    with pytest.raises(ValueError, match="must not be after"):
        ImeBackfillRequest(
            producer_code=5219,
            start_date=date(2026, 8, 19),
            end_date=date(2026, 8, 18),
        )

    request = ImeBackfillRequest(producer_code=5219, all_history=True)
    assert request.all_history is True
    assert ALL_HISTORY_START == date(2001, 3, 21)

    with pytest.raises(ValueError, match="must not be after"):
        ImeBackfillRequest(
            producer_code=5219,
            all_history=True,
            end_date=date(2001, 3, 20),
        )


@pytest.mark.asyncio
async def test_ime_backfill_api_rejects_disabled_producer() -> None:
    body = ImeBackfillRequest(
        producer_code=9999,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 18),
    )
    with patch("src.routes.admin_tasks.enabled_producer_codes", return_value=[5219]):
        with pytest.raises(HTTPException) as exc:
            await api_backfill_ime_physical_trades(_request(), body)

    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_ime_backfill_api_enqueues_all_history_with_visible_config() -> None:
    body = ImeBackfillRequest(producer_code=5219, all_history=True)
    row = SimpleNamespace(run_id="11111111-1111-1111-1111-111111111111")
    result = SimpleNamespace(id="celery-1")
    enqueue = MagicMock(return_value=(row, result))

    with (
        patch("src.routes.admin_tasks.enabled_producer_codes", return_value=[5219]),
        patch("src.routes.admin_tasks.enqueue_task", enqueue),
        patch("src.routes.admin_tasks.date") as mocked_date,
    ):
        mocked_date.today.return_value = date(2026, 8, 18)
        response = await api_backfill_ime_physical_trades(_request(), body)

    kwargs = enqueue.call_args.kwargs
    assert kwargs["kwargs"] == {
        "producer_code": 5219,
        "start_date_str": "2001-03-21",
        "end_date_str": "2026-08-18",
        "all_history": True,
    }
    assert kwargs["start_date"] == ALL_HISTORY_START
    assert kwargs["end_date"] == date(2026, 8, 18)
    assert response.collection_run_id == str(row.run_id)


@pytest.mark.asyncio
async def test_price_volume_api_requires_admin() -> None:
    with pytest.raises(HTTPException) as exc:
        await api_ime_price_volume(
            _request(authenticated=False),
            producer_code=5219,
            symbol="MAS-CPCANG32.5-L50-00",
            frm=date(2026, 8, 18),
            to=date(2026, 8, 18),
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_price_volume_api_rejects_reversed_range() -> None:
    with pytest.raises(HTTPException) as exc:
        await api_ime_price_volume(
            _request(),
            producer_code=5219,
            symbol="MAS-CPCANG32.5-L50-00",
            frm=date(2026, 8, 19),
            to=date(2026, 8, 18),
        )

    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_price_volume_api_rejects_product_outside_producer() -> None:
    producer = SimpleNamespace(enabled=True)
    session = MagicMock()
    session.get.side_effect = [producer, None]
    session_context = MagicMock()
    session_context.__enter__.return_value = session

    with patch("src.routes.ime.SessionLocal", return_value=session_context):
        with pytest.raises(HTTPException) as exc:
            await api_ime_price_volume(
                _request(),
                producer_code=5219,
                symbol="UNKNOWN",
                frm=date(2026, 8, 1),
                to=date(2026, 8, 18),
            )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_price_volume_api_returns_valid_empty_result() -> None:
    producer = SimpleNamespace(enabled=True)
    product = SimpleNamespace(goods_name="سیمان تیپ 2")
    session = MagicMock()
    session.get.side_effect = [producer, product]
    session_context = MagicMock()
    session_context.__enter__.return_value = session

    with (
        patch("src.routes.ime.SessionLocal", return_value=session_context),
        patch("src.routes.ime.get_ime_price_volume_points", AsyncMock(return_value=[])),
    ):
        response = await api_ime_price_volume(
            _request(),
            producer_code=5219,
            symbol="MAS-CPCANG32.5-L50-00",
            frm=date(2026, 8, 1),
            to=date(2026, 8, 18),
        )

    assert response["points"] == []


@pytest.mark.asyncio
async def test_acceptance_points_keep_cash_and_matching_separate() -> None:
    producer = SimpleNamespace(enabled=True)
    product = SimpleNamespace(goods_name="سیمان تیپ 2")
    session = MagicMock()
    session.get.side_effect = lambda _model, key: producer if key == 5219 else product
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    rows = [
        {
            "trade_date": date(2026, 8, 18),
            "jalali_date": "1405/05/27",
            "offer_id": "99123",
            "source_trade_pk": 88123,
            "contract_type": "نقدی",
            "price_thousand_rial": Decimal("35740"),
            "quantity": Decimal("1050"),
            "unit": "تن",
        },
        {
            "trade_date": date(2026, 8, 18),
            "jalali_date": "1405/05/27",
            "offer_id": "99123",
            "source_trade_pk": 88124,
            "contract_type": "نقدی (مچینگ)",
            "price_thousand_rial": Decimal("35740"),
            "quantity": Decimal("150"),
            "unit": "تن",
        },
    ]

    with (
        patch("src.routes.ime.SessionLocal", return_value=session_context),
        patch("src.routes.ime.get_ime_price_volume_points", AsyncMock(return_value=rows)),
    ):
        response = await api_ime_price_volume(
            _request(),
            producer_code=5219,
            symbol="MAS-CPCANG32.5-L50-00",
            frm=date(2026, 8, 18),
            to=date(2026, 8, 18),
        )

    assert [point["contract_type"] for point in response["points"]] == ["نقدی", "نقدی (مچینگ)"]
    assert [point["source_trade_pk"] for point in response["points"]] == [88123, 88124]
    assert [point["price_toman"] for point in response["points"]] == [3574000.0, 3574000.0]
    assert [point["quantity"] for point in response["points"]] == [1050.0, 150.0]


def test_postgres_migration_seeds_only_initial_enabled_producer() -> None:
    source = Path("alembic/versions/i9d0e1f2g3h4_add_ime_physical_market.py").read_text()

    assert '"ime_producers"' in source
    assert '"ime_products"' in source
    assert "VALUES (5219, 'سیمان مازندران', true)" in source
    assert source.count("VALUES (") == 1


def test_admin_navigation_registers_all_four_ime_views() -> None:
    source = Path("src/admin/__init__.py").read_text()

    for view in ("ImeProducerAdmin", "ImeProductAdmin", "ImeTradesView", "ImePriceVolumeView"):
        assert f"admin.add_view({view})" in source
