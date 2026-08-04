from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.admin._render import _TEMPLATE_ENV
from src.admin.option.iv_clickhouse_views import OptionIVPointsView, ORCWingFitsView
from src.db.clickhouse.iv_surface import (
    count_orc_wing_fits,
    get_iv_points_paginated,
)


async def test_iv_points_query_supports_valid_only_and_run_filters(mock_async_client: AsyncMock) -> None:
    mock_async_client.query.return_value = SimpleNamespace(
        column_names=["run_id", "rejection_reason"],
        result_rows=[("00000000-0000-0000-0000-000000000001", "")],
    )

    rows = await get_iv_points_paginated(
        run_id="00000000-0000-0000-0000-000000000001",
        trade_date=date(2026, 7, 8),
        rejection_reason="",
        offset=100,
        limit=25,
    )

    assert rows[0]["rejection_reason"] == ""
    query = mock_async_client.query.call_args.args[0]
    parameters = mock_async_client.query.call_args.kwargs["parameters"]
    assert "FROM `option_iv_points`" in query
    assert "rejection_reason = {rejection:String}" in query
    assert parameters["rejection"] == ""
    assert parameters["off"] == 100
    assert parameters["lim"] == 25


async def test_orc_fit_count_preserves_zero_and_quality_flag(mock_async_client: AsyncMock) -> None:
    mock_async_client.query.return_value = SimpleNamespace(result_rows=[(7,)])

    total = await count_orc_wing_fits(converged=0, quality_flag="insufficient_strikes")

    assert total == 7
    query = mock_async_client.query.call_args.args[0]
    parameters = mock_async_client.query.call_args.kwargs["parameters"]
    assert "converged = {converged:UInt8}" in query
    assert "has(quality_flags, {quality_flag:String})" in query
    assert parameters["converged"] == 0


async def test_iv_points_view_maps_valid_only_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    count = AsyncMock(return_value=1)
    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr("src.admin.option.iv_clickhouse_views.count_iv_points", count)
    monkeypatch.setattr("src.admin.option.iv_clickhouse_views.get_iv_points_paginated", fetch)
    view = object.__new__(OptionIVPointsView)
    filters = view.parse_filters({"rejection_reason": "__valid__", "side": "bid"})

    await view.fetch(filters, 0, 100)

    assert count.await_args.kwargs["rejection_reason"] == ""
    assert count.await_args.kwargs["side"] == "bid"
    assert fetch.await_args.kwargs["rejection_reason"] == ""


@pytest.mark.parametrize(
    "template_name",
    ["option/iv_points_list.html", "option/orc_wing_fits_list.html"],
)
def test_iv_record_templates_compile(template_name: str) -> None:
    _TEMPLATE_ENV.get_template(template_name)


def test_iv_record_views_are_options_analytics_pages() -> None:
    assert OptionIVPointsView.category == "Options Analytics"
    assert ORCWingFitsView.category == "Options Analytics"
    source = Path("src/admin/__init__.py").read_text()
    assert "admin.add_view(OptionIVPointsView)" in source
    assert "admin.add_view(ORCWingFitsView)" in source
