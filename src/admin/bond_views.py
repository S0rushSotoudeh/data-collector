from sqladmin import ModelView

from src.db.models.bond import BondInstrument


class BondInstrumentAdmin(ModelView, model=BondInstrument):
    name = "Bond Instrument"
    name_plural = "Bond Instruments"
    icon = "fa-solid fa-file-invoice"
    column_list = [
        BondInstrument.instrument_code,
        BondInstrument.symbol,
        BondInstrument.name_fa,
        BondInstrument.status,
        BondInstrument.maturity_date,
        BondInstrument.created_at,
    ]
    column_searchable_list = [
        BondInstrument.instrument_code,
        BondInstrument.symbol,
        BondInstrument.name_fa,
        BondInstrument.name_en,
    ]
    column_sortable_list = [
        BondInstrument.instrument_code,
        BondInstrument.symbol,
        BondInstrument.status,
        BondInstrument.maturity_date,
        BondInstrument.created_at,
    ]
    column_default_sort = [(BondInstrument.instrument_code, False)]
    can_create = True
    can_edit = True
    can_delete = False
    can_export = True
    page_size = 50