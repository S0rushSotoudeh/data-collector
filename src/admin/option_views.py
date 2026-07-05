from sqladmin import ModelView

from src.db.models.option import OptionInstrument


class OptionInstrumentAdmin(ModelView, model=OptionInstrument):
    name = "Option Instrument"
    name_plural = "Option Instruments"
    icon = "fa-solid fa-file-contract"
    column_list = [
        OptionInstrument.symbol,
        OptionInstrument.name_fa,
        OptionInstrument.status,
        OptionInstrument.option_type,
        OptionInstrument.strike_price,
        OptionInstrument.expiry_date,
        OptionInstrument.underlying_symbol,
        OptionInstrument.created_at,
    ]
    column_searchable_list = [
        OptionInstrument.instrument_code,
        OptionInstrument.symbol,
        OptionInstrument.name_fa,
        OptionInstrument.name_en,
        OptionInstrument.underlying_symbol,
    ]
    column_sortable_list = [
        OptionInstrument.instrument_code,
        OptionInstrument.symbol,
        OptionInstrument.status,
        OptionInstrument.expiry_date,
        OptionInstrument.strike_price,
        OptionInstrument.option_type,
        OptionInstrument.created_at,
    ]
    column_default_sort = [(OptionInstrument.expiry_date, True)]
    can_create = True
    can_edit = True
    can_delete = False
    can_export = True
    page_size = 50
