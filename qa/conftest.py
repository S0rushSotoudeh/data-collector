from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Browser, BrowserContext, Page


BASE_URL = os.getenv("E2E_BASE_URL", "https://data.nita.info").rstrip("/")
ARTIFACT_ROOT = Path(os.getenv("E2E_ARTIFACT_DIR", Path(__file__).parent / "artifacts"))
RUN_DIR = ARTIFACT_ROOT / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _credentials() -> tuple[str, str]:
    username = os.getenv("E2E_USERNAME", "")
    password = os.getenv("E2E_PASSWORD", "")
    if not username or not password:
        pytest.skip("Set E2E_USERNAME and E2E_PASSWORD to run authenticated stage checks.")
    return username, password


def pytest_configure(config: pytest.Config) -> None:
    config._qa_records = []  # type: ignore[attr-defined]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "base_url": BASE_URL,
        "finished_at": datetime.now(UTC).isoformat(),
        "exit_status": exitstatus,
        "records": getattr(session.config, "_qa_records", []),
    }
    (RUN_DIR / "coverage.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _login(page: Page) -> None:
    username, password = _credentials()
    page.goto(f"{BASE_URL}/admin/", wait_until="domcontentloaded")
    if "/login" not in page.url:
        return
    page.locator('input[name="username"]').fill(username)
    page.locator('input[name="password"]').fill(password)
    page.get_by_role("button", name=re.compile("login|sign in", re.I)).click()
    page.wait_for_load_state("domcontentloaded")
    assert "/login" not in page.url, "Stage authentication failed."


@pytest.fixture
def admin_page(browser: Browser, request: pytest.FixtureRequest) -> Page:
    context: BrowserContext = browser.new_context(
        viewport={"width": 1440, "height": 1080}, accept_downloads=True
    )
    page = context.new_page()
    console_errors: list[str] = []
    request_failures: list[str] = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: console_errors.append(str(error)))

    def on_response(response: Any) -> None:
        if response.status >= 500 and urlparse(response.url).netloc == urlparse(BASE_URL).netloc:
            request_failures.append(f"{response.status} {response.url}")

    page.on("response", on_response)
    _login(page)
    yield page

    failed = bool(getattr(request.node, "rep_call", None) and request.node.rep_call.failed)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    screenshot = None
    if failed or console_errors or request_failures:
        screenshot = f"{request.node.name}.png"
        page.screenshot(path=str(RUN_DIR / screenshot), full_page=True)
    request.config._qa_records.append({  # type: ignore[attr-defined]
        "test": request.node.nodeid,
        "status": "failed" if failed else "passed",
        "url": page.url,
        "console_errors": console_errors,
        "server_errors": request_failures,
        "screenshot": screenshot,
    })
    context.close()


def assert_clean_page(page: Page) -> None:
    assert page.locator("body").inner_text().strip(), "Page body is empty."
    assert not page.locator("text=/Internal Server Error|Traceback/i").count(), "Server error shown in page."


@pytest.fixture
def stage_url() -> str:
    return BASE_URL
