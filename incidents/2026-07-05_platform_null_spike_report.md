# Incident: platform null-rate spike on 2018-07-11 (simulated day)

- **Detected**: `monitor_platform_null_rate` (singular dbt test, severity
  warn) — WARN on the prod build at 2026-07-05 07:28:59 UTC, recorded in
  `analytics_elementary.elementary_test_results`.
- **Status**: resolved

## Symptom

`stg_floodit__events.platform` is null for **34.64%** of rows on simulated
day **2018-07-11** (17,320 of 50,000 events). All other loaded days: 0.00%.
Healthy baseline for this column is exactly zero nulls (verified over the
full export range during Phase 1 recon).

## Evidence

| # | Check | Command/query | Finding |
|---|---|---|---|
| 1 | Alerting monitors, last 48h | capped query on `elementary_test_results` | Only `stg_floodit__events` singular-test WARNs; no volume, schema, or mart-test alerts |
| 2 | Pinpoint by day | capped query, `platform` null rate per `event_date >= 2018-07-08` | 0.0 / 0.0 / 0.0 / **0.3464** — single-day, single-column |
| 3 | Freshness | `dbt source freshness --target prod` | PASS — loader cadence is healthy, not a stall |
| 4 | Volume | `INFORMATION_SCHEMA.PARTITIONS`, capped | 50,000 rows on every recent day incl. 07-11 — **not** a duplicate/partial load |
| 5 | Loader state | `replay_loader --status` | next shard 2018-07-12, 30 days loaded — pointer healthy |
| 6 | Recent changes | `git log -15` | No model/loader logic change touching `platform`; recent commits are the monitoring/agent layers themselves |

## Root cause

**Injected data-quality incident**: `loader/incidents.py --null-spike
platform 0.35` rewrote partition `events$20180711` (per the runbook, this
is the documented query-load exception — 37,748,736 bytes billed, capped).
The evidence signature matches the runbook's null-spike row exactly:
single day, single column, volume and freshness clean, ~35% null rate ≈
the injected probability. Confirmed against the injection log line
(`Injected null-spike 35% on events.platform for 2018-07-11`).

## Blast radius

From `manifest.json` `child_map`, everything downstream of
`stg_floodit__events` (8 models, 2 exposures):

- `int_events_sessionized`, `int_user_days` — unaffected in practice
  (do not read `platform`)
- `fct_events.platform` — nulls persisted for 07-11 (incremental lookback
  rewrote the day)
- `dim_users.platform` — users whose *first* observed event fell on 07-11
  may carry a null platform
- `daily_active_users`, `retention_cohorts`, `level_funnel_daily`,
  `extra_steps_economy_daily` — row counts unaffected; none group by
  platform today, so **metric values are not distorted**, but any future
  platform split over 07-11 would be
- Exposures `engagement_dashboard`, `game_economy_review` — downstream of
  the above (placeholders in v1)

## Fix

Operational (runbook §recovery) — no code change needed:

```sh
uv run python -m loader.replay_loader --day 2018-07-11   # idempotent re-copy of the pristine shard
cd dbt && uv run dbt build --target prod                 # rebuild lookback + re-run monitors
```

Executed 2026-07-05 ~07:31 UTC: re-copy restored 50,000 clean rows;
follow-up prod build **PASS 95 / WARN 0** — `monitor_platform_null_rate`
green. Resolved.

## Follow-ups

- None structural: detection worked on the first scheduled run after
  injection, pinpointing took four capped queries (< 60 MB total scanned).
- If platform splits become first-class metrics, add a `not_null` test on
  `fct_events.platform` scoped to post-fix days so the failure blocks marts
  instead of warning.
