from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect


pytestmark = pytest.mark.stateful
STAGE_DATE = os.getenv("E2E_STAGE_TRADE_DATE", "2026-08-11")


def _enabled() -> None:
    if os.getenv("E2E_ENABLE_STATEFUL") != "1":
        pytest.skip("Set E2E_ENABLE_STATEFUL=1 to permit a new stage analysis run.")


def _first_real_option(page: Page, selector: str) -> str:
    options = page.locator(f"{selector} option")
    for index in range(options.count()):
        value = options.nth(index).get_attribute("value")
        if value:
            return value
    pytest.skip(f"No selectable value available for {selector}.")


def _queue_and_assert_run(page: Page, button: str, endpoint: str) -> None:
    with page.expect_response(
        lambda response: endpoint in response.url and response.request.method == "POST",
        timeout=20_000,
    ) as pending:
        page.locator(button).click()
    response = pending.value
    assert response.ok, response.text()
    data = response.json()
    assert data.get("run_id") and data.get("task_id"), data


def test_queue_minimal_parity_run(admin_page: Page, stage_url: str) -> None:
    _enabled()
    admin_page.goto(f"{stage_url}/admin/options-parity", wait_until="domcontentloaded")
    admin_page.locator("#underlying").select_option("17914401175772326")
    admin_page.locator("#call").select_option("19119603381147142")
    admin_page.locator("#start-date").fill(STAGE_DATE)
    admin_page.locator("#end-date").fill(STAGE_DATE)
    admin_page.locator("#start-time").fill("10:00:00")
    admin_page.locator("#end-time").fill("10:01:00")
    admin_page.locator("#multiplier").fill("1000")
    _queue_and_assert_run(admin_page, 'button[type="submit"]', "/admin/tasks/run-parity-analysis")


def test_queue_minimal_box_run(admin_page: Page, stage_url: str) -> None:
    _enabled()
    admin_page.goto(f"{stage_url}/admin/options-box-spread", wait_until="domcontentloaded")
    expect(admin_page.locator("#trade-date option")).not_to_have_count(0, timeout=15_000)
    admin_page.locator("#trade-date").select_option(_first_real_option(admin_page, "#trade-date"))
    for selector in ("#underlying", "#expiry", "#lower", "#upper", "#convention"):
        expect(admin_page.locator(selector)).to_be_enabled(timeout=15_000)
        admin_page.locator(selector).select_option(_first_real_option(admin_page, selector))
    admin_page.locator("#start").fill("10:00:00")
    admin_page.locator("#end").fill("10:01:00")
    _queue_and_assert_run(admin_page, 'button:has-text("Queue analysis")', "/admin/tasks/run-box-spread")


def test_queue_minimal_iv_run(admin_page: Page, stage_url: str) -> None:
    _enabled()
    admin_page.goto(f"{stage_url}/admin/options-iv-surface", wait_until="domcontentloaded")
    admin_page.locator("#underlying").select_option("17914401175772326")
    admin_page.locator("#start-date").fill(STAGE_DATE)
    admin_page.locator("#end-date").fill(STAGE_DATE)
    admin_page.locator("#session-start").fill("10:00:00")
    admin_page.locator("#session-end").fill("10:01:00")
    admin_page.locator("#i30").check()
    admin_page.locator("#convention").select_option(_first_real_option(admin_page, "#convention"))
    _queue_and_assert_run(admin_page, 'button:has-text("Queue replay")', "/admin/tasks/run-iv-surface")


def test_preview_then_queue_minimal_mispricing_run(admin_page: Page, stage_url: str) -> None:
    _enabled()
    admin_page.goto(f"{stage_url}/admin/options-mispricing", wait_until="domcontentloaded")
    admin_page.locator("#trade-date").fill(STAGE_DATE)
    admin_page.locator("#start-time").fill("10:00:00")
    admin_page.locator("#end-time").fill("10:01:00")
    admin_page.locator("#convention").select_option(_first_real_option(admin_page, "#convention"))
    with admin_page.expect_response(lambda response: "universe-preview" in response.url, timeout=20_000) as preview:
        admin_page.locator("#preview-button").click()
    assert preview.value.ok
    expect(admin_page.locator("#preview-card")).not_to_have_class("d-none", timeout=15_000)
    _queue_and_assert_run(admin_page, 'button:has-text("Freeze and queue run")', "/admin/tasks/run-option-mispricing")
