from __future__ import annotations

import os
import re
from dataclasses import dataclass

import pytest
from playwright.sync_api import Page, expect

from conftest import assert_clean_page


@dataclass(frozen=True)
class Route:
    path: str
    heading: str


ROUTES = (
    Route("/admin/options-parity", "Put–Call Parity"),
    Route("/admin/options-box-spread", "Box-Spread"),
    Route("/admin/options-market-potential", "Options Market Potential"),
    Route("/admin/options-iv-surface", "Historical Executable IV"),
    Route("/admin/options-mispricing", "Option Mispricing"),
    Route("/admin/option-iv-points", "Executable IV Points"),
    Route("/admin/orc-wing-fits", "ORC Wing Fits"),
    Route("/admin/option-pricing-convention/list", "Pricing"),
    Route("/admin/parity-analysis-runs", "Parity Runs"),
    Route("/admin/parity-analysis-snapshots", "Parity"),
    Route("/admin/box-spread-runs", "Box-Spread Runs"),
    Route("/admin/box-spread-snapshots", "Box-Spread"),
    Route("/admin/box-spread-pricings", "Box-Spread"),
    Route("/admin/iv-orc-runs", "IV/ORC Runs"),
    Route("/admin/option-mispricing-runs", "Mispricing Runs"),
    Route("/admin/market-potential-runs", "Market-Potential Runs"),
)

PARITY_RUN_ID = os.getenv("E2E_PARITY_RUN_ID", "fd8a8204-e7a3-4a89-9770-3b7f05087bc9")
BOX_RUN_ID = os.getenv("E2E_BOX_RUN_ID", "77b8c867-f1e6-4d88-9001-b0c0dd1b606f")
IV_RUN_ID = os.getenv("E2E_IV_RUN_ID", "7e2253eb-716a-4076-9fc6-1e71e8fb732c")
MISPRICING_RUN_ID = os.getenv("E2E_MISPRICING_RUN_ID", "646492eb-0410-4a4a-83cb-fd07b624cb73")


@pytest.mark.parametrize("route", ROUTES, ids=lambda item: item.path.rsplit("/", 1)[-1] or "options")
def test_all_options_routes_are_authenticated_and_render(admin_page: Page, stage_url: str, route: Route) -> None:
    response = admin_page.goto(f"{stage_url}{route.path}", wait_until="domcontentloaded")
    assert response and response.ok, f"Route returned {response.status if response else 'no response'}"
    expect(admin_page.get_by_text(re.compile(re.escape(route.heading), re.I)).first).to_be_visible(timeout=10_000)
    assert_clean_page(admin_page)


@pytest.mark.parametrize("path", [route.path for route in ROUTES[5:]])
def test_history_lists_accept_invalid_filters_and_deep_pages(admin_page: Page, stage_url: str, path: str) -> None:
    response = admin_page.goto(
        f"{stage_url}{path}?page=9999&run_id=not-a-real-run&status=not-a-real-status",
        wait_until="domcontentloaded",
    )
    assert response and response.ok
    assert_clean_page(admin_page)
    assert "Traceback" not in admin_page.content()


def test_parity_instrument_chain_and_known_run(admin_page: Page, stage_url: str) -> None:
    admin_page.goto(f"{stage_url}/admin/options-parity?run_id={PARITY_RUN_ID}", wait_until="domcontentloaded")
    underlying = admin_page.locator("#underlying")
    expect(underlying).to_be_visible()
    underlying.select_option("17914401175772326")
    expect(admin_page.locator("#call option")).not_to_have_count(0)
    admin_page.locator("#call").select_option("19119603381147142")
    expect(admin_page.locator("#put option")).not_to_have_count(0)
    expect(admin_page.locator("#put")).to_have_value(re.compile(".+"))
    expect(admin_page.locator("#saved-runs option")).not_to_have_count(0, timeout=10_000)
    assert_clean_page(admin_page)


def test_parity_verified_regression_is_reported_by_ui(admin_page: Page, stage_url: str) -> None:
    admin_page.goto(f"{stage_url}/admin/options-parity?run_id={PARITY_RUN_ID}", wait_until="domcontentloaded")
    expect(admin_page.locator("#run-status")).to_contain_text(re.compile("Loaded|legacy", re.I), timeout=15_000)
    body = admin_page.locator("body").inner_text()
    assert "Legacy edge logic" in body
    assert "No valid snapshots" in body or "YTM metrics unavailable" in body


@pytest.mark.live_data
def test_box_saved_run_charts_records_and_csv(admin_page: Page, stage_url: str) -> None:
    admin_page.goto(f"{stage_url}/admin/options-box-spread?run_id={BOX_RUN_ID}", wait_until="domcontentloaded")
    expect(admin_page.locator("#runs option")).not_to_have_count(0, timeout=15_000)
    expect(admin_page.locator("canvas").first).to_be_visible(timeout=15_000)
    for selector in ("#snapshot-link", "#pricing-link", "#csv"):
        href = admin_page.locator(selector).get_attribute("href")
        assert href and BOX_RUN_ID in href


@pytest.mark.live_data
def test_iv_run_timeline_controls_charts_and_export(admin_page: Page, stage_url: str) -> None:
    admin_page.goto(f"{stage_url}/admin/options-iv-surface?run_id={IV_RUN_ID}", wait_until="domcontentloaded")
    expect(admin_page.locator("#runs option")).not_to_have_count(0, timeout=15_000)
    expect(admin_page.locator("#time")).to_be_visible()
    expect(admin_page.locator("#expiry option")).not_to_have_count(0, timeout=15_000)
    admin_page.locator("#side").select_option("ask")
    expect(admin_page.locator("canvas").first).to_be_visible(timeout=15_000)
    href = admin_page.locator("#csv").get_attribute("href")
    assert href and IV_RUN_ID in href
    assert_clean_page(admin_page)


@pytest.mark.live_data
def test_mispricing_preview_ranking_and_csv(admin_page: Page, stage_url: str) -> None:
    admin_page.goto(f"{stage_url}/admin/options-mispricing?run_id={MISPRICING_RUN_ID}", wait_until="domcontentloaded")
    expect(admin_page.locator("#runs option")).not_to_have_count(0, timeout=15_000)
    expect(admin_page.locator("#ranking-body")).not_to_contain_text("Select a completed run.", timeout=15_000)
    href = admin_page.locator("#csv").get_attribute("href")
    assert href and MISPRICING_RUN_ID in href
    rows_before = admin_page.locator("#ranking-body tr").count()
    admin_page.locator("#rank-sort").select_option("median")
    expect(admin_page.locator("#ranking-body tr")).to_have_count(rows_before, timeout=15_000)


def test_market_potential_populated_and_empty_dates(admin_page: Page, stage_url: str) -> None:
    admin_page.goto(f"{stage_url}/admin/options-market-potential", wait_until="domcontentloaded")
    admin_page.locator("#start").fill("2026-08-11")
    admin_page.locator("#end").fill("2026-08-11")
    admin_page.locator("#refresh").click()
    expect(admin_page.locator("#coverage-state")).not_to_contain_text("Auditing", timeout=15_000)
    assert admin_page.locator("#contracts").inner_text() != "—"
    admin_page.locator("#start").fill("2020-01-01")
    admin_page.locator("#end").fill("2020-01-01")
    admin_page.locator("#refresh").click()
    expect(admin_page.locator("#coverage-state")).not_to_contain_text("Auditing", timeout=15_000)


@pytest.mark.live_data
def test_exports_download_for_live_analytics_views(admin_page: Page, stage_url: str) -> None:
    cases = (
        (f"/admin/options-box-spread?run_id={BOX_RUN_ID}", "#csv"),
        (f"/admin/options-iv-surface?run_id={IV_RUN_ID}", "#csv"),
        (f"/admin/options-mispricing?run_id={MISPRICING_RUN_ID}", "#csv"),
        ("/admin/options-market-potential", 'a[href*="export.csv"]'),
    )
    for path, selector in cases:
        admin_page.goto(f"{stage_url}{path}", wait_until="domcontentloaded")
        expect(admin_page.locator(selector)).to_be_visible(timeout=15_000)
        with admin_page.expect_download(timeout=20_000) as download_info:
            admin_page.locator(selector).click()
        assert download_info.value.suggested_filename.endswith(".csv")


def test_navigation_and_mobile_layout(admin_page: Page, stage_url: str) -> None:
    admin_page.goto(f"{stage_url}/admin/options-parity", wait_until="domcontentloaded")
    admin_page.goto(f"{stage_url}/admin/options-iv-surface", wait_until="domcontentloaded")
    admin_page.go_back(wait_until="domcontentloaded")
    assert "/options-parity" in admin_page.url
    admin_page.set_viewport_size({"width": 390, "height": 844})
    admin_page.reload(wait_until="domcontentloaded")
    overflow = admin_page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 2, f"Mobile page has horizontal overflow of {overflow}px."
