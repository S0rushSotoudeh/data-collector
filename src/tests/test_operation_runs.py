from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

from src.admin._render import _TEMPLATE_ENV
from src.admin.run_views import (
    BoxSpreadRunsView,
    CollectionRunsView,
    IVORCRunsView,
    MarketPotentialRunsView,
    OperationRunsView,
    ParityRunsView,
    YieldCurveRunsView,
)
from src.celery_app import celery, create_scheduled_operation_run, fail_operation_run
from src.services.operation_runs import RunProgressReporter, TASK_SPECS, finish_run
from src.db.clickhouse.iv_surface import get_fits, get_points
from src.tasks import backfill_yield_curves


def test_every_application_task_has_an_operation_spec() -> None:
    registered = {name for name in celery.tasks if name.startswith("src.tasks.")}
    assert set(TASK_SPECS) == registered


def test_application_imports_all_registered_routes() -> None:
    from src.main import app

    assert app.title == "Data Collector API"


def test_family_pages_share_one_run_view_contract() -> None:
    views = (
        CollectionRunsView,
        YieldCurveRunsView,
        MarketPotentialRunsView,
        ParityRunsView,
        IVORCRunsView,
        BoxSpreadRunsView,
    )
    assert all(issubclass(view, OperationRunsView) for view in views)
    assert {view.family for view in views} == {
        "collection", "yield_curve", "market_potential", "parity", "iv_orc", "box_spread",
    }
    _TEMPLATE_ENV.get_template("operations/run_list.html")


def test_scheduled_publish_creates_and_propagates_run_id() -> None:
    identifier = uuid.uuid4()
    headers = {"id": "celery-task-id"}
    with patch(
        "src.celery_app.create_for_task_message",
        return_value=SimpleNamespace(run_id=identifier),
    ) as create:
        create_scheduled_operation_run(
            sender="src.tasks.fetch_yesterday_option_orderbook",
            body=([], {}, {}),
            headers=headers,
        )
    assert headers["operation_run_id"] == str(identifier)
    assert headers["operation_trigger"] == "scheduled"
    create.assert_called_once()


def test_manual_publish_is_not_duplicated() -> None:
    headers = {"id": "celery-task-id", "operation_run_id": str(uuid.uuid4())}
    with patch("src.celery_app.create_for_task_message") as create:
        create_scheduled_operation_run(
            sender="src.tasks.fetch_yesterday_option_orderbook",
            body=([], {}, {}),
            headers=headers,
        )
    create.assert_not_called()


def test_failure_signal_uses_sender_request_headers() -> None:
    run_id = str(uuid.uuid4())
    sender = SimpleNamespace(
        request=SimpleNamespace(headers={"operation_run_id": run_id}, id="task-id")
    )
    with patch("src.celery_app.fail_run") as fail:
        fail_operation_run(sender=sender, exception=RuntimeError("boom"))
    fail.assert_called_once()
    assert fail.call_args.args[0] == run_id


def test_finish_run_uses_completed_and_skipped_states() -> None:
    run_id = uuid.uuid4()
    stored = SimpleNamespace(progress_total=10, progress_current=3)
    with (
        patch("src.services.operation_runs.get_run", return_value=stored),
        patch("src.services.operation_runs.update_run") as update,
    ):
        finish_run(run_id, {"total_rows": 25, "warning_count": 2})
        assert update.call_args.kwargs["status"] == "completed"
        assert update.call_args.kwargs["progress_current"] == 10
        assert update.call_args.kwargs["output_count"] == 25

        finish_run(run_id, {"status": "skipped", "reason": "outside market hours"})
        assert update.call_args.kwargs["status"] == "skipped"


def test_progress_reporter_persists_every_five_percent_and_at_completion() -> None:
    run_id = uuid.uuid4()
    with patch("src.services.operation_runs.update_progress") as update:
        progress = RunProgressReporter(run_id)
        progress.set_total(100)
        for _ in range(4):
            progress.advance(output_count=2)
        assert update.call_count == 1

        progress.advance(output_count=2)
        assert update.call_count == 2
        assert update.call_args.kwargs["current"] == 5
        assert update.call_args.kwargs["output_count"] == 10

        for _ in range(95):
            progress.advance()
        assert update.call_count == 21
        assert update.call_args.kwargs["current"] == 100


def test_progress_reporter_checkpoints_absolute_progress_and_result() -> None:
    run_id = uuid.uuid4()
    with patch("src.services.operation_runs.update_progress") as update:
        progress = RunProgressReporter(run_id)
        progress.set_total(100)
        for current in range(1, 101):
            progress.checkpoint(
                current,
                output_count=current * 2,
                warning_count=current // 10,
                result={"fit_count": current},
            )

        assert [call.kwargs["current"] for call in update.call_args_list] == [
            0, *range(5, 101, 5)
        ]
        assert update.call_args.kwargs["output_count"] == 200
        assert update.call_args.kwargs["warning_count"] == 10
        assert update.call_args.kwargs["result"] == {"fit_count": 100}


def test_yield_curve_backfill_reports_each_pending_date() -> None:
    first = date(2026, 8, 20)
    second = date(2026, 8, 21)
    client = AsyncMock()
    client.query.side_effect = [
        SimpleNamespace(result_rows=[(first,), (second,)]),
        SimpleNamespace(result_rows=[]),
    ]
    curve_results = [
        {"date": first.isoformat(), "fits": 4, "bonds": 6},
        {"date": second.isoformat(), "fits": 0, "error": "No instruments found"},
    ]
    run_id = uuid.uuid4()

    with (
        patch("src.tasks._operation_run_id", return_value=str(run_id)),
        patch("src.db.clickhouse.get_async_client", return_value=client),
        patch("src.analytics.engine.compute_curve_for_date", AsyncMock(side_effect=curve_results)),
        patch("src.services.operation_runs.update_progress") as update,
    ):
        result = backfill_yield_curves.run(first.isoformat(), second.isoformat())

    assert [call.kwargs["current"] for call in update.call_args_list] == [0, 1, 2]
    assert update.call_args.kwargs["total"] == 2
    assert update.call_args.kwargs["output_count"] == 10
    assert update.call_args.kwargs["warning_count"] == 1
    assert result == {
        "dates_processed": 2,
        "dates_skipped": 0,
        "total_rows": 10,
        "warning_count": 1,
    }


def test_iv_running_update_can_refresh_local_state_without_database_write() -> None:
    from src.analytics.iv_engine import _update_run

    stored = {
        "run_id": str(uuid.uuid4()),
        "completed_snapshot_count": 5,
        "point_count": 10,
        "fit_count": 3,
        "warning_count": 1,
    }
    with (
        patch("src.analytics.iv_engine.update_progress") as progress,
        patch("src.analytics.iv_engine.update_run") as update,
    ):
        updated = _update_run(
            None,
            stored,
            "running",
            persist_progress=False,
            completed_snapshot_count=10,
        )

    assert updated["completed_snapshot_count"] == 10
    progress.assert_not_called()
    update.assert_not_called()


def test_analysis_engines_no_longer_import_legacy_run_writers() -> None:
    import src.analytics.iv_engine as iv_engine
    import src.analytics.parity_engine as parity_engine

    assert not hasattr(iv_engine, "insert_run")
    assert not hasattr(parity_engine, "insert_run")


async def test_iv_output_queries_do_not_use_final_on_mergetree(mock_async_client) -> None:
    """IV points and ORC fits are append-only MergeTree output tables."""
    mock_async_client.query.return_value.column_names = []
    mock_async_client.query.return_value.result_rows = []

    await get_points(str(uuid.uuid4()))
    points_query = mock_async_client.query.call_args.args[0]
    assert " FINAL " not in points_query

    await get_fits(str(uuid.uuid4()))
    fits_query = mock_async_client.query.call_args.args[0]
    assert " FINAL " not in fits_query
