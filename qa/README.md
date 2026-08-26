# Options Analytics QA

This suite tests the authenticated stage server without changing application code or deleting data. Results, screenshots, browser errors, and timing evidence are written under `qa/artifacts/` and are intentionally untracked.

Set the credentials only in your shell, never in a committed file:

```powershell
$env:E2E_USERNAME = "..."
$env:E2E_PASSWORD = "..."
$env:E2E_BASE_URL = "https://data.nita.info"
```

Run the safe regression coverage:

```powershell
docker compose --profile qa run --rm qa pytest qa/test_options_readonly.py
```

Run the stateful workflows only when a new minimal stage run is authorized:

```powershell
$env:E2E_ENABLE_STATEFUL = "1"
docker compose --profile qa run --rm qa pytest -m stateful qa/test_options_stateful.py
```

Run moderate read-only load stages. Each stage lasts 60 seconds and contains no job-creation traffic:

```powershell
docker compose --profile qa run --rm qa locust -f qa/locustfile.py --headless -u 2 -r 2 -t 60s --host $env:E2E_BASE_URL --csv qa/artifacts/load-2
docker compose --profile qa run --rm qa locust -f qa/locustfile.py --headless -u 5 -r 2 -t 60s --host $env:E2E_BASE_URL --csv qa/artifacts/load-5
docker compose --profile qa run --rm qa locust -f qa/locustfile.py --headless -u 10 -r 2 -t 60s --host $env:E2E_BASE_URL --csv qa/artifacts/load-10
```

Locust exits non-zero when failures exceed 1% or aggregate p95 exceeds 10 seconds. Stop manually if stage jobs become unhealthy or authentication starts failing.
