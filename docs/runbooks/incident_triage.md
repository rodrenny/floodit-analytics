# Runbook: incident injection & triage

The replay pipeline has a deterministic incident injector
([loader/incidents.py](../../loader/incidents.py)) so monitoring and the
triage workflow can be exercised on demand. Each injector produces exactly
one failure class.

## Injectors → detectors

| Injector | What it does | Cost | Detected by |
|---|---|---|---|
| `--skip-day` | Next loader run loads nothing (decrements a `skip_runs` counter in `replay_state`) | free (state write) | `dbt source freshness`: metadata age crosses `warn_after: 26h` after one missed daily run, `error_after: 50h` after two |
| `--duplicate-day` | Re-appends the last day's shard onto its partition (~100k rows instead of 50k) | free (copy job, WRITE_APPEND) | `monitor_daily_volume_in_expected_band` (singular test, warn): any day outside 40k–60k rows |
| `--drop-column COL` | Rewrites the last day with COL fully nulled | **query-based load — the documented cost-policy exception**; capped 2 GiB + partition-filtered | `monitor_platform_null_rate` (singular test, warn) when COL=platform; dbt `not_null` tests for tested columns |
| `--null-spike COL PCT` | Same, nulling only PCT of rows | same exception | `monitor_platform_null_rate` — fires above 1% nulls |

**Why deterministic monitors instead of Elementary anomaly tests:** the
replay writes data with 2018 event timestamps, but Elementary's anomaly
detection anchors its training/detection windows to wall-clock now — on
replayed data those tests pass vacuously (verified during Phase 4: an
injected 100k-row day sailed through `volume_anomalies`). Elementary stays
for what is run-based and replay-proof: `schema_changes` monitoring and the
`elementary_test_results` store that feeds the monitoring report. The
volume band (40k–60k; the export ships exactly 50k/day) and null-rate
(>1%) monitors are deterministic dbt tests — sharper than a trained
baseline on this dataset, and their results flow into the same report.

All four accept `--day YYYY-MM-DD` to target a specific day (except
`--skip-day`, which acts on the schedule, not the data).

```sh
uv run python -m loader.incidents --duplicate-day
uv run python -m loader.incidents --null-spike platform 0.4
```

## Where alerts surface

1. The scheduled `replay` workflow runs loader → `dbt build --target prod`
   (Elementary anomaly monitors run inside the build at severity `warn` —
   they alert without halting the marts) → `dbt source freshness` →
   **monitoring report artifact** (`monitoring-report`, Markdown), built by
   [.github/scripts/monitoring_report.py](../../.github/scripts/monitoring_report.py)
   from `analytics_elementary.elementary_test_results`.
2. A freshness `error` fails the workflow run itself — that red run is the
   pager, GitHub notifies the repo owner.

## Triage flow

1. Open the failed/alerting `replay` run; download `monitoring-report`.
2. Identify the failure class from the table above — each maps 1:1 to a
   cause in this simulated pipeline.
3. Check loader logs in the run (`INCIDENT INJECTION` lines are explicit)
   and `replay_state` (`--status`).
4. Recover:
   - skip-day: nothing to fix — the next run resumes; or run the loader
     manually with `--catch-up N` to close the gap.
   - duplicate-day / drop-column / null-spike: re-copy the day, then rebuild.
     The re-copy is always the same (idempotent WRITE_TRUNCATE restores the
     pristine shard):

     ```sh
     uv run python -m loader.replay_loader --day <YYYY-MM-DD>
     ```

     **The rebuild depends on how old the repaired day is**, because
     `fct_events` is incremental with a 2-day lookback:

     - *Recent day* (within the last 2 loaded days): a normal
       `dbt build --target prod` picks it up — the default lookback covers it.
     - *Older day*: the default lookback does **not** reach it. Rebuild
       `fct_events` from the repaired day forward, which also refreshes the
       downstream marts (they are tables, rebuilt in full each run):

       ```sh
       cd dbt && uv run dbt build --target prod --select fct_events+ \
         --vars '{rebuild_start_date: "<YYYY-MM-DD>"}'
       ```

       `insert_overwrite` replaces only the partitions from that day forward,
       so the repair propagates without a full-table refresh.
5. `/triage-incident` automates steps 1–4 into an RCA report + draft fix PR.
