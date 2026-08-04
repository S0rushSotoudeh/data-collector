from types import SimpleNamespace
from unittest.mock import patch
import uuid

from src.admin._render import _TEMPLATE_ENV
from src.admin.run_views import (
    CollectionRunsView,
    IVORCRunsView,
    MarketPotentialRunsView,
    OperationRunsView,
    ParityRunsView,
    YieldCurveRunsView,
)
from src.celery_app import celery, create_scheduled_operation_run, fail_operation_run
from src.services.operation_runs import TASK_SPECS, finish_run
from src.db.clickhouse.iv_surface import get_fits, get_points


def test_every_application_task_has_an_operation_spec() -> None:
    registered = {name for name in celery.tasks if name.startswith("src.tasks.")}
    assert set(TASK_SPECS) == registered


def test_family_pages_share_one_run_view_contract() -> None:
    views = (
        CollectionRunsView,
        YieldCurveRunsView,
        MarketPotentialRunsView,
        ParityRunsView,
        IVORCRunsView,
    )
    assert all(issubclass(view, OperationRunsView) for view in views)
    assert {view.family for view in views} == {
        "collection", "yield_curve", "market_potential", "parity", "iv_orc",
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
