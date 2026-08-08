import csv
import io
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.admin._render import _TEMPLATE_ENV
from src.admin.option.iv_clickhouse_views import OptionIVPointsView, ORCWingFitsView
from src.db.clickhouse.iv_surface import (
    count_orc_wing_fits,
    get_history,
    get_iv_points_paginated,
    get_snapshot_fits,
    get_snapshot_points,
    get_snapshot_rejection_counts,
    get_timeline,
)
from src.routes.iv_surface import _csv_stream


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


async def test_iv_timeline_uses_compact_distinct_queries(mock_async_client: AsyncMock) -> None:
    mock_async_client.query.side_effect = [
        SimpleNamespace(result_rows=[]),
        SimpleNamespace(result_rows=[(datetime(2026, 8, 1, 8, 30),)]),
        SimpleNamespace(result_rows=[(date(2026, 9, 1),)]),
    ]

    snapshots, expiries = await get_timeline("00000000-0000-0000-0000-000000000001")

    assert snapshots == [datetime(2026, 8, 1, 8, 30)]
    assert expiries == [date(2026, 9, 1)]
    queries = [call.args[0] for call in mock_async_client.query.call_args_list if call.args[0] != "SELECT 1"]
    assert all("SELECT DISTINCT" in query for query in queries)
    assert all("run_id = {rid:UUID}" in query for query in queries)


async def test_snapshot_queries_are_scoped_to_one_run_and_time(mock_async_client: AsyncMock) -> None:
    point_time = datetime(2026, 8, 1, 8, 30)
    mock_async_client.query.return_value = SimpleNamespace(
        column_names=["snapshot_time", "expiry_date", "side", "option_type", "strike", "forward", "iv"],
        result_rows=[(point_time, date(2026, 9, 1), "bid", "put", 100.0, 101.0, .2)],
    )

    rows = await get_snapshot_points("00000000-0000-0000-0000-000000000001", point_time)

    assert rows[0]["iv"] == .2
    query = mock_async_client.query.call_args.args[0]
    assert "snapshot_time = {snapshot:DateTime64(3)}" in query
    assert "rejection_reason = ''" in query

    mock_async_client.query.return_value = SimpleNamespace(
        column_names=["snapshot_time", "converged"], result_rows=[(point_time, 1)]
    )
    await get_snapshot_fits("00000000-0000-0000-0000-000000000001", point_time)
    assert "snapshot_time = {snapshot:DateTime64(3)}" in mock_async_client.query.call_args.args[0]

    mock_async_client.query.return_value = SimpleNamespace(result_rows=[("", 5), ("missing_quote", 2)])
    counts = await get_snapshot_rejection_counts("00000000-0000-0000-0000-000000000001", point_time)
    assert counts == {"": 5, "missing_quote": 2}


async def test_history_queries_only_request_selected_expiry_and_side(mock_async_client: AsyncMock) -> None:
    mock_async_client.query.side_effect = [
        SimpleNamespace(result_rows=[]),
        SimpleNamespace(column_names=["snapshot_time", "vc"], result_rows=[]),
        SimpleNamespace(column_names=["snapshot_time", "forward"], result_rows=[]),
    ]

    await get_history("00000000-0000-0000-0000-000000000001", date(2026, 9, 1), "ask")

    queries = [call.args[0] for call in mock_async_client.query.call_args_list if call.args[0] != "SELECT 1"]
    assert "expiry_date = {expiry:Date}" in queries[0]
    assert "side = {side:String}" in queries[0]
    assert "LIMIT 1 BY snapshot_time" in queries[1]


def test_iv_csv_streams_blocks_without_a_row_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    columns = tuple(f"value-{index}" for index, _ in enumerate(__import__("src.db.clickhouse.iv_surface", fromlist=["POINT_COLUMNS"]).POINT_COLUMNS))
    monkeypatch.setattr("src.routes.iv_surface.stream_points", lambda _run_id: [[columns], [columns]])
    run = {
        "config_json": "{}", "interval_seconds": 10,
        "pricing_convention_version": "2026-08-01", "model_version": "orc-wing-v1",
    }

    rows = list(csv.reader(io.StringIO("".join(_csv_stream("run-id", run)))))

    assert len(rows) == 3
    assert rows[1][0] == "value-0"
    assert rows[1][-1] == "orc-wing-v1"


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
