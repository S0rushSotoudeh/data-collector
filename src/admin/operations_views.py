from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqladmin import ModelView

from src.db.models.operations import OptionFeeSchedule, OptionPricingConvention
from src.db.session import SessionLocal


TEHRAN = ZoneInfo("Asia/Tehran")
TSETMC_PRESET_NOTES = (
    "Standard TSETMC equity-option preset. Review exchange notices for contract-specific "
    "adjustments before approval."
)


class OptionPricingConventionAdmin(ModelView, model=OptionPricingConvention):
    name = "Pricing convention"
    name_plural = "Pricing conventions"
    icon = "fa-solid fa-file-signature"
    category = "Options Analytics"
    can_create = False
    can_delete = False
    column_list = [
        OptionPricingConvention.name, OptionPricingConvention.contract_family,
        OptionPricingConvention.effective_from, OptionPricingConvention.effective_to,
        OptionPricingConvention.exercise_style, OptionPricingConvention.black76_compatible,
        OptionPricingConvention.approved, OptionPricingConvention.approver,
    ]
    form_excluded_columns = [
        OptionPricingConvention.convention_id,
        OptionPricingConvention.approver,
        OptionPricingConvention.approved_at,
        OptionPricingConvention.created_at,
        OptionPricingConvention.updated_at,
    ]
    form_args = {
        "name": {"default": "TSETMC Equity Options — Black-76"},
        "contract_family": {"default": "tsetmc_equity_option"},
        "effective_from": {"default": date(2016, 12, 18)},
        "exercise_style": {"default": "European"},
        "settlement_style": {"default": "cash_and_physical"},
        "multiplier": {"default": 1000},
        "tick_size": {"default": 1.0},
        "price_unit": {"default": "IRR"},
        "black76_compatible": {"default": True},
        "reference_source": {
            "default": "Tehran Stock Exchange option contract notices (https://www.tse.ir/)"
        },
        "notes": {"default": TSETMC_PRESET_NOTES},
    }

    async def on_model_change(self, data, model, is_created, request) -> None:
        """Make approval a single deliberate checkbox in the admin UI."""
        if data.get("approved"):
            if is_created or not getattr(model, "approved_at", None):
                data["approved_at"] = datetime.now(TEHRAN)
            data["approver"] = (
                getattr(model, "approver", None)
                or request.session.get("user")
                or "admin"
            )
        else:
            data["approved_at"] = None
            data["approver"] = None


class OptionFeeScheduleAdmin(ModelView, model=OptionFeeSchedule):
    name = "Option fee schedule"
    name_plural = "Option fee schedules"
    icon = "fa-solid fa-percent"
    category = "Options Analytics"
    can_create = True
    can_edit = True
    can_delete = False
    column_list = [
        OptionFeeSchedule.market, OptionFeeSchedule.effective_from,
        OptionFeeSchedule.effective_to, OptionFeeSchedule.buy_rate,
        OptionFeeSchedule.sell_rate, OptionFeeSchedule.settlement_cost_per_contract,
        OptionFeeSchedule.source,
    ]
    form_excluded_columns = [
        OptionFeeSchedule.fee_schedule_id,
        OptionFeeSchedule.created_at,
        OptionFeeSchedule.updated_at,
    ]
    form_args = {
        "market": {"default": "tse"},
        "effective_from": {"default": date(2026, 6, 16)},
        "source": {"default": "doc/quant/fees.md"},
    }

    async def on_model_change(self, data, model, is_created, request) -> None:
        start = data["effective_from"]
        end = data.get("effective_to")
        if end is not None and end < start:
            raise ValueError("effective_to must not be before effective_from")
        current_id = getattr(model, "fee_schedule_id", None)
        with SessionLocal() as session:
            statement = select(OptionFeeSchedule).where(
                OptionFeeSchedule.market == data["market"],
                OptionFeeSchedule.effective_from <= (end or date.max),
                or_(
                    OptionFeeSchedule.effective_to.is_(None),
                    OptionFeeSchedule.effective_to >= start,
                ),
            )
            if current_id is not None:
                statement = statement.where(OptionFeeSchedule.fee_schedule_id != current_id)
            if session.execute(statement).scalars().first() is not None:
                raise ValueError("fee schedule dates overlap an existing row for this market")
