from types import SimpleNamespace

import pytest

from src.admin.operations_views import OptionPricingConventionAdmin


def test_tsetmc_pricing_convention_form_is_prefilled() -> None:
    defaults = OptionPricingConventionAdmin.form_args

    assert OptionPricingConventionAdmin.can_create is False
    assert OptionPricingConventionAdmin.can_delete is False
    assert defaults["name"]["default"] == "TSETMC Equity Options — Black-76"
    assert defaults["exercise_style"]["default"] == "European"
    assert defaults["settlement_style"]["default"] == "cash_and_physical"
    assert defaults["multiplier"]["default"] == 1000
    assert defaults["tick_size"]["default"] == 1.0
    assert defaults["price_unit"]["default"] == "IRR"
    assert defaults["black76_compatible"]["default"] is True


@pytest.mark.asyncio
async def test_approval_is_attributed_and_timestamped() -> None:
    data = {"approved": True}
    model = SimpleNamespace(approved_at=None, approver=None)
    request = SimpleNamespace(session={"user": "reviewer"})

    await OptionPricingConventionAdmin.on_model_change(
        SimpleNamespace(), data, model, False, request
    )

    assert data["approver"] == "reviewer"
    assert data["approved_at"] is not None
    assert data["approved_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_unapproval_clears_audit_fields() -> None:
    data = {"approved": False}
    model = SimpleNamespace(approved_at=object(), approver="reviewer")
    request = SimpleNamespace(session={"user": "reviewer"})

    await OptionPricingConventionAdmin.on_model_change(
        SimpleNamespace(), data, model, False, request
    )

    assert data["approver"] is None
    assert data["approved_at"] is None
