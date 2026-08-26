from __future__ import annotations

import os

from locust import HttpUser, between, events, task


PARITY_RUN_ID = os.getenv("E2E_PARITY_RUN_ID", "fd8a8204-e7a3-4a89-9770-3b7f05087bc9")
IV_RUN_ID = os.getenv("E2E_IV_RUN_ID", "7e2253eb-716a-4076-9fc6-1e71e8fb732c")
MAX_FAILURE_RATIO = float(os.getenv("QA_MAX_FAILURE_RATIO", "0.01"))
MAX_P95_MS = int(os.getenv("QA_MAX_P95_MS", "10000"))


class OptionsReadOnlyUser(HttpUser):
    wait_time = between(0.2, 0.8)

    def on_start(self) -> None:
        username = os.getenv("E2E_USERNAME", "")
        password = os.getenv("E2E_PASSWORD", "")
        if not username or not password:
            raise RuntimeError("E2E_USERNAME and E2E_PASSWORD are required for load testing.")
        response = self.client.post("/admin/login", data={"username": username, "password": password}, name="login")
        if response.status_code >= 400:
            raise RuntimeError(f"Stage login failed: {response.status_code}")

    @task(4)
    def list_pages(self) -> None:
        for path in (
            "/admin/option-iv-points?page=100",
            "/admin/orc-wing-fits?page=100",
            "/admin/parity-analysis-snapshots?page=2",
            "/admin/box-spread-pricings?page=2",
        ):
            self.client.get(path, name="options list/filter")

    @task(2)
    def analytics_pages(self) -> None:
        self.client.get(f"/admin/options-parity?run_id={PARITY_RUN_ID}", name="parity chart page")
        self.client.get(f"/admin/options-iv-surface?run_id={IV_RUN_ID}", name="iv chart page")

    @task(2)
    def chart_data(self) -> None:
        self.client.get(f"/api/v1/parity-analysis/runs/{PARITY_RUN_ID}/snapshots", name="parity snapshots API")
        self.client.get(f"/api/v1/iv-surface/runs/{IV_RUN_ID}/timeline", name="iv timeline API")

    @task(1)
    def market_potential_filter(self) -> None:
        self.client.get(
            "/api/v1/options/market-potential/timeseries?start_date=2026-08-11&end_date=2026-08-11&limit=5000",
            name="market potential filter API",
        )


@events.quitting.add_listener
def enforce_stop_thresholds(environment, **_: object) -> None:
    stats = environment.stats.total
    p95 = stats.get_response_time_percentile(0.95) or 0
    if stats.fail_ratio > MAX_FAILURE_RATIO or p95 > MAX_P95_MS:
        environment.process_exit_code = 1
