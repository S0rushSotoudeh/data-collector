from unittest.mock import MagicMock

from src.db.clickhouse.schema import ensure_tables, ORDER_BOOK_TABLE, TRADES_TABLE


class TestSchema:
    def test_ensure_tables_creates_both_tables(self, mock_ch_client: MagicMock) -> None:
        ensure_tables()

        assert mock_ch_client.command.call_count == 5
        ddl1 = mock_ch_client.command.call_args_list[1][0][0]
        ddl2 = mock_ch_client.command.call_args_list[2][0][0]
        ddl3 = mock_ch_client.command.call_args_list[3][0][0]
        ddl4 = mock_ch_client.command.call_args_list[4][0][0]

        assert ORDER_BOOK_TABLE in ddl1
        assert TRADES_TABLE in ddl2
        assert "yield_curve_fits" in ddl3
        assert "yield_curve_bonds" in ddl4

    def test_ddl_uses_merge_tree_not_replicated(self) -> None:
        from src.db.clickhouse.schema import _ORDER_BOOK_DDL, _TRADES_DDL

        assert "ReplicatedMergeTree" not in _ORDER_BOOK_DDL
        assert "ReplicatedMergeTree" not in _TRADES_DDL
        assert "MergeTree" in _ORDER_BOOK_DDL
        assert "MergeTree" in _TRADES_DDL

    def test_ddl_includes_ttl(self) -> None:
        from src.db.clickhouse.schema import _ORDER_BOOK_DDL, _TRADES_DDL

        assert _ORDER_BOOK_DDL.count("TTL") == 1
        assert "INTERVAL 1 YEAR" in _ORDER_BOOK_DDL
        assert "ingested_at" in _ORDER_BOOK_DDL
        assert _TRADES_DDL.count("TTL") == 1
        assert "INTERVAL 1 YEAR" in _TRADES_DDL
        assert "ingested_at" in _TRADES_DDL

    def test_ddl_uses_int64_not_float64(self) -> None:
        from src.db.clickhouse.schema import _ORDER_BOOK_DDL, _TRADES_DDL

        assert "Float64" not in _ORDER_BOOK_DDL
        assert "Float64" not in _TRADES_DDL
        assert "Int64" in _ORDER_BOOK_DDL
        assert "Int64" in _TRADES_DDL

    def test_passed_client_used(self) -> None:
        mock = MagicMock()
        ensure_tables(mock)
        mock.command.assert_called()