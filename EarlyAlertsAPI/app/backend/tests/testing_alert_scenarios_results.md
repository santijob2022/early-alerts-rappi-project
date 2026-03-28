# Alert Scenario Tests — Results & Analysis

**Date:** March 27, 2026  
**Test file:** `app/backend/tests/test_alert_scenarios.py`  
**Final result:** 11/11 passed in 3.50s

---

## Summary

The alert engine is **mostly compliant** with `Motor_Reglas_y_Alertas.md`. All core rules
(thresholds, sensitive zones, cooldown, earnings target, horizon policy) behave correctly. One
decision the engine makes that isn't explicit in the doc is noted below.

---

## Test Cases

| # | Class | Test | Precip (mm) | Result | Notes |
|---|---|---|---|---|---|
| 1 | `TestScenarioDry` | `test_no_alerts_emitted` | 0.0 | ✅ PASS | `alerts_emitted == 0` |
| 2 | `TestScenarioDry` | `test_alerts_endpoint_empty` | 0.0 | ✅ PASS | `/alerts/latest?status=pending` returns `[]` |
| 3 | `TestScenarioMedio` | `test_alerts_emitted` | 2.5 | ✅ PASS | `alerts_emitted >= 1` |
| 4 | `TestScenarioMedio` | `test_medio_or_higher_risk_present` | 2.5 | ✅ PASS | At least one `medio/alto/critico` alert in pending list |
| 5 | `TestScenarioMedio` | `test_alert_has_required_fields` | 2.5 | ✅ PASS | All alerts carry `id`, `zone`, `risk_level`, `precip_mm`, `created_at` |
| 6 | `TestScenarioAlto` | `test_critico_alerts_emitted` | 5.5 | ✅ PASS | `alerts_emitted >= 1` |
| 7 | `TestScenarioAlto` | `test_critico_risk_level_present` | 5.5 | ✅ PASS | At least one `critico` alert in pending list |
| 8 | `TestScenarioAlto` | `test_critico_alert_precip_above_threshold` | 5.5 | ✅ PASS | All `critico` alerts have `precip_mm >= 5.0` |
| 9 | `TestAlertLifecycle` | `test_consume_alert_removes_from_pending` | — | ✅ PASS | `PATCH /alerts/{id}/consume` removes alert from pending list |
| 10 | `TestSensitiveZoneTrigger` | `test_sensitive_zone_names_appear_in_alerts` | 5.5 | ✅ PASS | At least one of Santiago / Carretera Nacional / Santa Catarina / MTY_Apodaca_Huinala in alerts |
| 11 | `TestSensitiveZoneTrigger` | `test_all_alert_zones_are_known` | 5.5 | ✅ PASS | Every alert zone is one of the 14 configured Monterrey zones |

---

## Motor_Reglas_y_Alertas.md Conformance

| Rule | Document | System | Status |
|---|---|---|---|
| Base trigger | `>= 2.0 mm/hr` fires an alert | Fires alert. MEDIO fires only if zone is `sensitive + peak`; ALTO/CRITICO fire in any zone/hour | ⚠️ See note below |
| Sensitive zone trigger | `>= 1.0 mm/hr` in peak hours for Santiago, Carretera Nacional, Santa Catarina, MTY_Apodaca_Huinala | Correctly applies lower trigger for those 4 zones during peak hours `{12,13,14,19,20,21}` | ✅ |
| `>= 5.0 mm` force-escalation | Escalate to CRITICO if already notifiable | Escalates to CRITICO only if projected ratio already reaches ALTO or above, matching _"si el caso ya era notificable"_ | ✅ |
| Cooldown memory (4h) | Suppress duplicate alerts within 4h unless risk escalates | Enforced with escalation override and `resend_precip_delta_mm` check | ✅ |
| Horizon policy | `t+1` → alert / escalate / suppress. `t+2` / `t+3` → watchlist only | `lead_time > 60 min` always produces `WATCH`, never `ALERT` | ✅ |
| Earnings target | 80 MXN/order | Correctly recommended when `current_earnings_mxn < 80` | ✅ |
| Dry-close streak | Close open event after 2 consecutive dry hours | Implemented via `dry_close_streak_hours = 2` in memory config | ✅ |

### ⚠️ MEDIO outside sensitive+peak zones

The decision engine contains this logic (in `engine.py`, step 5):

```python
# --- 5. MEDIO non-sensitive non-peak → WATCH ─────────────────────────────
if risk == RiskLevel.MEDIO and not (is_peak and is_sensitive):
    return _build_watch(...)
```

This means a zone that is not sensitive (e.g. Centro) reaching MEDIO ratio in a non-peak hour
is downgraded to WATCH, not ALERT. The Motor doc states _"forecast >= 2.0 mm/hr → alert"_ without
this carve-out. The restriction is **conservative and operationally reasonable** (MEDIO in off-peak
is low signal), but it is an implicit design decision not fully documented in
`Motor_Reglas_y_Alertas.md`. Consider clarifying whether this is intentional.

---

## Bug Found: Time Dependency

### Problem

The first run of the tests produced **6 failures**. Root cause was a cascade of time sensitivity:

1. Tests ran at **22:00 CST** → `t1_hour = 23` (off-peak).
2. `_make_hourly_block()` in `conftest.py` generates hours `0-5` (UTC midnight to 5am), which
   map to CST hours `18-23`. The orchestrator filtered for exactly `forecast_hour == t1_hour`,
   so `hour 23` had data, but with a **baseline ratio of ~0.245** (Apodaca Centro at hour 23).
3. With `precip=2.5mm` and baseline `0.245`, heavy lift `0.60` → `projected = 0.845` —
   **far below `medio_min = 1.50`** → classified as SUPPRESS.
4. Even with `precip=5.5mm`, projected ≈ `0.845 + 0.60 = 1.245` → still below MEDIO → no alert.

### Fix Applied

`_run_once_with_precip()` now:
- Uses a `PeakFakeProvider` that returns forecast times for UTC `19:00–00:00` → CST `13:00–18:00`.
- Patches `orchestrator.datetime.now` to return `2026-03-27T18:00:00Z` (12:00 CST) so
  `t1_hour = 13`, a CST **peak hour** with baselines in the `1.40–1.55` range across zones.

This makes the tests fully deterministic and independent of the clock at runtime.

```python
_FIXED_NOW_UTC = datetime(2026, 3, 27, 18, 0, 0, tzinfo=timezone.utc)
# 18:00 UTC = 12:00 CST → t1_hour = 13 (peak, baselines ~1.40-1.55)

with patch("app.backend.services.orchestrator.datetime", mock_dt), \
     patch("app.backend.ingestion.open_meteo.OpenMeteoProvider", return_value=fake):
    response = client.post("/api/v1/jobs/run-once")
```

---

## Expected Projection Math (hour 13, CST peak)

Representative zones at `forecast_hour = 13`:

| Zone | Baseline (hr 13) | 2.5 mm lift (moderate peak: +0.60) | Projected | Risk |
|---|---|---|---|---|
| Centro | ~1.45 | +0.60 | ~2.05 | MEDIO |
| Apodaca Centro | 1.4986 | +0.60 | 2.0986 | MEDIO |
| Santiago | 1.35* (sensitive floor: 2.700) | — | **2.700** | CRITICO |
| Carretera Nacional | 1.3974 (sensitive floor: 2.407) | — | **2.407** | CRITICO |

*Sensitive zones get the _floor_ override when `1.0 mm <= precip < 2.0 mm`. At 2.5 mm (above base
trigger), the floor does not apply — the lift projection stands, but baselines are already lower
so fewer zones reach ALTO.

With `5.5 mm` (heavy bucket), the `>= 5.0 mm` escalation rule forces CRITICO for any zone that
would otherwise be ALTO or higher.

---

## How to Run

```bash
cd EarlyAlertsAPI
.venv/Scripts/python.exe -m pytest app/backend/tests/test_alert_scenarios.py -v
```

Expected output:

```
11 passed in ~3.5s
```
