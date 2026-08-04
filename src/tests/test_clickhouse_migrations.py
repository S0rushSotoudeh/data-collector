import importlib
from unittest.mock import MagicMock, patch

import pytest

from src.db.clickhouse.migrations.manager import (
    MIGRATIONS_TABLE,
    _ensure_migrations_table,
    _get_applied_versions,
    _discover_versions,
    _mark_applied,
    _mark_removed,
    upgrade,
    downgrade,
    history,
    pending,
    check,
)


class TestMigrationManagerInternals:
    def test_ensure_migrations_table_creates_table(self) -> None:
        client = MagicMock()
        _ensure_migrations_table(client)
        ddl = client.command.call_args[0][0]
        assert MIGRATIONS_TABLE in ddl
        assert "CREATE TABLE IF NOT EXISTS" in ddl

    def test_get_applied_versions_returns_sorted(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = [(3,), (1,)]
        versions = _get_applied_versions(client)
        assert versions == [3, 1]

    def test_get_applied_versions_empty(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = []
        versions = _get_applied_versions(client)
        assert versions == []

    def test_discover_versions_finds_all(self) -> None:
        versions = _discover_versions()
        assert 1 in versions
        assert 2 in versions
        assert 3 in versions
        module_path_1, short_name_1 = versions[1]
        assert "001_create_schema_migrations" in module_path_1
        assert short_name_1 == "001_create_schema_migrations.py"
        module_path_2, short_name_2 = versions[2]
        assert "002_create_bond_order_book" in module_path_2
        assert short_name_2 == "002_create_bond_order_book.py"
        module_path_3, short_name_3 = versions[3]
        assert "003_create_bond_trades" in module_path_3
        assert short_name_3 == "003_create_bond_trades.py"
        assert "012_add_parity_ytm_metrics" in versions[12][0]

    def test_mark_applied_inserts_row(self) -> None:
        client = MagicMock()
        _mark_applied(client, 5, "005_test")
        sql = client.command.call_args[0][0]
        assert MIGRATIONS_TABLE in sql
        assert "5" in sql
        assert "005_test" in sql

    def test_mark_removed_deletes_row(self) -> None:
        client = MagicMock()
        _mark_removed(client, 5)
        sql = client.command.call_args[0][0]
        assert MIGRATIONS_TABLE in sql
        assert "DELETE WHERE version = 5" in sql


class TestUpgrade:
    def test_upgrade_applies_all_pending(self) -> None:
        applied = []

        def track_applied(client, version, name):
            applied.append(version)

        client = MagicMock()
        client.query.return_value.result_rows = []

        with (
            patch("src.db.clickhouse.migrations.manager.get_client", return_value=client),
            patch("src.db.clickhouse.migrations.manager._mark_applied", side_effect=track_applied),
        ):
            new_versions = upgrade()

        assert len(new_versions) == 13
        assert applied == list(range(1, 14))

    def test_upgrade_skips_already_applied(self) -> None:
        applied = []

        def track_applied(client, version, name):
            applied.append(version)

        client = MagicMock()
        client.query.return_value.result_rows = [(1,), (2,)]

        with (
            patch("src.db.clickhouse.migrations.manager.get_client", return_value=client),
            patch("src.db.clickhouse.migrations.manager._mark_applied", side_effect=track_applied),
        ):
            new_versions = upgrade()

        assert new_versions == list(range(3, 14))
        assert applied == list(range(3, 14))

    def test_upgrade_all_already_applied(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = [(version,) for version in range(1, 14)]

        with patch("src.db.clickhouse.migrations.manager.get_client", return_value=client):
            new_versions = upgrade()

        assert new_versions == []

    def test_upgrade_with_explicit_client(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = []

        new_versions = upgrade(client)

        assert len(new_versions) == 13

    def test_parity_ytm_migration_is_additive_and_reversible(self) -> None:
        migration = importlib.import_module(
            "src.db.clickhouse.migrations.versions.012_add_parity_ytm_metrics"
        )
        client = MagicMock()

        migration.upgrade(client)

        commands = [call.args[0] for call in client.command.call_args_list]
        assert len(commands) == 33
        assert all("ADD COLUMN IF NOT EXISTS" in command for command in commands)
        assert any("minimum_ytm_spread_bps" in command for command in commands)
        assert any("make_call_ask_capital_per_contract" in command for command in commands)
        assert any("make_underlying_bid_ytm_spread_bps" in command for command in commands)

        client.reset_mock()
        migration.downgrade(client)
        assert all(
            "DROP COLUMN IF EXISTS" in call.args[0]
            for call in client.command.call_args_list
        )


class TestDowngrade:
    def test_downgrade_reverts_last(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = [(1,), (2,), (3,), (4,)]

        result = downgrade(client)

        assert result == 4
        # Verify mark_removed was called
        sql = client.command.call_args_list[-1][0][0]
        assert "DELETE WHERE version = 4" in sql

    def test_downgrade_no_migrations_applied(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = []

        with pytest.raises(RuntimeError, match="No migrations have been applied"):
            downgrade(client)

    def test_downgrade_missing_version_file(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = [(999,)]

        with pytest.raises(RuntimeError, match="is applied but no version file found"):
            downgrade(client)


class TestHistory:
    def test_history_returns_all_applied(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = [
            (1, "001_test", "2024-01-01 00:00:00"),
            (2, "002_test", "2024-01-02 00:00:00"),
        ]

        rows = history(client)

        assert len(rows) == 2
        assert rows[0]["version"] == 1
        assert rows[0]["name"] == "001_test"
        assert rows[1]["version"] == 2

    def test_history_empty(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = []

        rows = history(client)
        assert rows == []


class TestPending:
    def test_pending_returns_unapplied(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = [(1,)]

        p = pending(client)

        assert 2 in p
        assert 3 in p
        assert 4 in p
        assert 5 in p
        assert 6 in p
        assert 7 in p
        assert 8 in p
        assert 9 in p
        assert 10 in p
        assert 12 in p
        assert 1 not in p

    def test_pending_none(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = [(version,) for version in range(1, 14)]

        p = pending(client)
        assert p == []


class TestCheck:
    def test_check_true_when_up_to_date(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = [(version,) for version in range(1, 14)]

        assert check(client) is True

    def test_check_false_when_pending(self) -> None:
        client = MagicMock()
        client.query.return_value.result_rows = [(1,)]

        assert check(client) is False
