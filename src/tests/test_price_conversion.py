from src.db.clickhouse import price_to_storage, price_from_storage


class TestPriceConversion:
    def test_price_to_storage_truncates_float(self) -> None:
        assert price_to_storage(842190.75) == 842190

    def test_price_to_storage_integer(self) -> None:
        assert price_to_storage(842190) == 842190

    def test_price_from_storage(self) -> None:
        assert price_from_storage(842190) == 842190.0

    def test_price_from_storage_zero(self) -> None:
        assert price_from_storage(0) == 0.0

    def test_roundtrip(self) -> None:
        original = 842190
        stored = price_to_storage(original)
        retrieved = price_from_storage(stored)
        assert retrieved == float(original)