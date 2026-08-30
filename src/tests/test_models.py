from datetime import date

import pytest
from pydantic import ValidationError
from sqlmodel import Field, SQLModel

from src.db.models import BondInstrument, StockInstrument


class TestBondInstrument:
    def test_create_valid(self) -> None:
        b = BondInstrument(instrument_code="12345")
        assert b.instrument_code == "12345"
        assert b.last_trade_date is None
        assert b.instrument_id is None

    def test_last_trade_date_as_date(self) -> None:
        b = BondInstrument(instrument_code="12345", last_trade_date=date(2026, 6, 16))
        assert b.last_trade_date == date(2026, 6, 16)

    def test_instrument_code_required(self) -> None:
        with pytest.raises(ValidationError):
            BondInstrument.model_validate({})

    def test_instrument_id_unique(self) -> None:
        field = BondInstrument.model_fields["instrument_id"]
        assert field.default is None

    def test_table_name(self) -> None:
        assert BondInstrument.__tablename__ == "bond_instruments"

    def test_has_indexes(self) -> None:
        args = BondInstrument.__table_args__
        assert args is not None
        names = {idx.name for idx in args if hasattr(idx, "name")}
        assert "idx_bond_symbol" in names
        assert "idx_bond_status" in names
        assert "idx_bond_maturity" in names


class TestStockInstrument:
    def test_isin_is_not_unique_but_instrument_id_is(self) -> None:
        table = StockInstrument.__table__
        assert table.c.isin.unique is not True
        assert table.c.instrument_id.unique is True
