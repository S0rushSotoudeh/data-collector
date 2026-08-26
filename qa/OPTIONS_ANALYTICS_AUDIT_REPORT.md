# Options Analytics Stage Audit — 2026-08-15

## Coverage

- All 16 Options Analytics routes were opened through the authenticated stage browser.
- Core saved-run workflows were loaded for Parity, Box Spread, IV/ORC, Mispricing, and Market Potential.
- Filters, deep pagination, responsive layout, charts, saved-run links, and Market Potential CSV export were checked.
- Browser console errors: none observed.
- New job submissions were not repeated in this pass; existing audit runs remain traceable by ID.

## Verified defects

### OPA-001 — High — Put–Call Parity rejects a valid اهرم pair

**Classification:** Functional correctness / data integrity  
**Affected pages:** `/admin/options-parity`, `/admin/parity-analysis-snapshots`

**Evidence:** Run `fd8a8204-e7a3-4a89-9770-3b7f05087bc9` loaded successfully in the UI as **YTM logic** with 301 snapshots and six rendered charts. The strategy KPI still states **No valid snapshots**. The corresponding snapshots page with `quality_status=valid` returns **0 records**.

**Reproduction:**

1. Open Put–Call Parity.
2. Select underlying `اهرم` (`17914401175772326`).
3. Select call `ضهرم5034` (`19119603381147142`, strike 50,000, expiry 2026-08-19) and put `طهرم5034` (`7601281576818295`).
4. Run 2026-08-11 from 10:00 to 12:30 at 30-second intervals with multiplier 1,000.
5. Load the resulting run, then filter its snapshots by `valid`.

**Expected:** Synchronized, positive two-sided quotes for this known good pair should produce at least one valid calculated snapshot and populated YTM/KPI fields.

**Actual:** All 301 snapshots are rejected, KPI fields contain no valid result, and the valid-snapshot filter is empty. This prevents the analytics workflow from identifying opportunities for a valid market pair.

### OPA-002 — Medium — Market Potential overflows horizontally on mobile

**Classification:** Visual/layout / usability  
**Affected page:** `/admin/options-market-potential`

**Reproduction:**

1. Open Market Potential at a 390px-wide viewport.
2. Inspect the full page width.

**Expected:** The responsive table containers should preserve a 390px document width and contain overflow locally.

**Actual:** The document is 466px wide, creating 76px of page-level horizontal scrolling. Both the Pilot-ready call/put packages table and the Contract concentration table extend to roughly 455–456px beyond the viewport.

## Performance result

Read-only browser load used authenticated tabs against IV Points, ORC Fits, Parity Snapshots, Box Pricings, Parity, and IV/ORC. No job-creation endpoints were called and no failed responses or console errors occurred.

| Concurrent users | Duration | Completed navigations | p50 | p95 |
| --- | ---: | ---: | ---: | ---: |
| 2 | 66s | 42 | 2.20s | 4.82s |
| 5 | 61s | 65 | 2.82s | 6.02s |
| 10 | 61s | 90 | 3.51s | 7.86s |

### OPA-003 — Medium — Analytics pages exceed the responsiveness target under moderate read-only load

**Classification:** Performance/usability  
**Affected area:** Options Analytics list and saved-run pages

The approved 10-user stage check reproduced a p95 of 7.86 seconds with no errors. This exceeds the 5-second analytics interaction target. The result is an end-to-end browser measurement rather than server-only timing, so follow-up should attribute latency by route/API before diagnosing the cause.

## Observations not classified as defects

- The Box Spread audit run `77b8c867-f1e6-4d88-9001-b0c0dd1b606f` loaded 481 snapshots and six charts, but had zero execution-grade timestamps and zero pricing cases. Its diagnostic conditions are consistent with the recorded input-quality gates, so it is not reported as a product defect.
- The IV run `7e2253eb-716a-4076-9fc6-1e71e8fb732c` rendered seven charts and its timeline/CSV controls. Its initially selected snapshot reported stale quotes and zero valid fits; this is retained as a data-timing observation rather than a defect.
- Market Potential returned populated results for 2026-08-11 and started a CSV download successfully. Empty/early market periods are not classified as defects unless coverage is misrepresented.
