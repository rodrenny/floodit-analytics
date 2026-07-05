# floodit-analytics

An analytics engineering repository over real mobile-game telemetry — the
public [Flood-It!](https://play.google.com/store/apps/details?id=com.labpixies.flood)
GA4 export (`firebase-public-project.analytics_153293282.events_*`, 114
daily-sharded tables, ~5.7M nested events) — built to demonstrate an
AI-amplified analytics workflow: agents draft the models, tests, docs, and
incident reports; layered machine gates (linting, contracts, cost caps,
data diffs) do the blocking; a human reviews and merges.

> **Status: under construction.** Phases 0 (conventions & scaffolding),
> 1 (infra + dbt foundation), 2 (replay loader), 3 (CI guardrails), and
> 4 (marts, monitoring, incident injection) are done. Every number in this
> README comes from a query or run that actually happened, and nothing is
> written here before it does.

## Cost guardrails — verified, not assumed

Both blocking layers were deliberately tripped and the failures recorded
(2026-07-05, project `data-eng-491120`):

| Guardrail | Deliberate violation | Observed result |
|---|---|---|
| `maximum_bytes_billed` (per-query cap) | Full-range scan (~185 MiB needed) under a 100 MB cap | Job failed, reason `bytesBilledLimitExceeded`: *"Query exceeded limit for bytes billed: 104857600. 193986560 or higher required."* `totalBytesBilled = 0` — nothing was billed. |
| `require_partition_filter` (schema-level) | Unfiltered `select count(*)` on `raw_floodit.events` | Rejected by BigQuery at validation: *"Cannot query over table 'data-eng-491120.raw_floodit.events' without a filter over column(s) '_PARTITION_LOAD_TIME', '_PARTITIONDATE', '_PARTITIONTIME'"*. |

The full layered inventory (caps → partition enforcement → free-by-design
operations → daily quota → budget alert) lives in
[docs/architecture.md](docs/architecture.md#guardrail-inventory).

## Verified so far (Phase 1)

- `terraform apply`: 12 resources — 4 datasets, the partitioned raw table,
  CI service account + least-privilege IAM, €5/month budget alert.
- `dbt build --select staging`: **8/8 PASS** (view + 7 tests) on the 7-day
  dev slice — 350,000 events, 2,399 distinct users, 2018-07-01→07-07;
  0 bytes for the view build, ~636 MiB total for the test suite, all under
  the 2 GiB dev cap.
- Public dataset recon (metadata + three capped queries ≤ 38 MiB each):
  114 shards, 2018-06-12 → 2018-10-03, 5.7M events, 3.87 GiB total.

## Verified so far (Phase 2)

- Replay loader: two consecutive runs loaded `events$20180612` and
  `events$20180613` (50,000 rows each) via **copy jobs only** — the loader
  contains no query job; state itself is written with load jobs and read
  with `tabledata.list`, both free.
- Idempotency: re-copying 2018-06-12 left the partition byte-identical
  (numRows 50,000 / numBytes 33,901,717 before and after) and did not
  advance state.
- `dbt source freshness --target prod`: **PASS** (metadata-based, age 58s
  at check time).
- `dbt build --target prod --select staging` over the replayed raw table:
  **8/8 PASS**.
- 15 loader unit tests cover sequencing, clamping at the last shard,
  state round-trips, and a fake client that fails the suite if the loader
  ever calls a non-free BigQuery method.

## Verified so far (Phase 3) — the CI gates, tripped on purpose

Two real acceptance PRs, run against live CI
(lint → slim build + contract guard → cost gate → data diff, WIF auth,
no key files):

| PR | Intent | Outcome |
|---|---|---|
| [#1 — docs: clarify board param](https://github.com/rodrenny/floodit-analytics/pull/1) | Clean pass | All 4 gates green ([run](https://github.com/rodrenny/floodit-analytics/actions/runs/28724175217)); cost gate dry-ran the modified model at **132.5 MiB — pass** and posted the bytes table as a PR comment. |
| [#2 — deliberately over-budget model](https://github.com/rodrenny/floodit-analytics/pull/2) | Must be blocked | `stg_floodit__events_wide_scan` dry-ran at **1,735.8 MiB > 1,024 MiB limit → cost_gate failed** ([run](https://github.com/rodrenny/floodit-analytics/actions/runs/28724190811)), data diff skipped by fail-fast, merge impossible under branch protection. Closed unmerged. |

The violation model was sized deliberately at ~1.7 GiB — inside the window
between the 1 GiB CI cost gate and the 2 GiB `maximum_bytes_billed` build
cap — to prove the *gate itself* fires, not the byte cap behind it.
Branch protection on `main` requires all four checks; agents open PRs,
humans merge.

## Verified so far (Phase 4) — marts, monitoring, incidents

- **Modeling** ([PR #4](https://github.com/rodrenny/floodit-analytics/pull/4)):
  gap-based sessionization (this export predates `ga_session_id`), six
  contracted marts, 51 tests — `dbt build` 60 PASS / 0 ERROR on the dev
  slice; funnel invariants pre-verified across all 114 days before being
  encoded as tests; D7 retention correctly **null** (not zero) where the
  horizon is unobservable.
- **Schema evolution absorbed**: the GA4 export grows 4 fields mid-window;
  the raw table now carries the superset schema and free copy jobs keep
  working for all 114 shards (probe-verified before adopting — see
  [architecture.md](docs/architecture.md#schema-evolution-discovered-during-replay)).
- **Monitoring**: Elementary for schema-change monitoring and the results
  store; volume/null-rate monitors as deterministic dbt tests, because
  Elementary's wall-clock-anchored anomaly windows are vacuous on
  2018-replayed data — found by testing, documented in the
  [runbook](docs/runbooks/incident_triage.md). Prod build: 95 PASS
  including monitors; per-run Markdown monitoring report artifact.
- **All four incident injectors fired their monitor, live:**
  duplicate-day (50,000 → 100,000 rows) → volume monitor **WARN**;
  null-spike platform 40% → null-rate monitor **WARN**; drop-column
  platform → null-rate monitor **WARN**; skip-day → loader logged the
  injection and left the table unmodified (freshness crosses
  `warn_after: 26h` at the next daily cron). Each was recovered with an
  idempotent one-day re-copy and the monitor re-verified green.

## Layout

| Path | What lives there |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Engineering conventions — the contract agents and humans follow |
| [docs/setup.md](docs/setup.md) | GCP, local, and CI setup |
| [infra/](infra/) | Terraform: datasets, CI service account, IAM (minimal by design) |
| [loader/](loader/) | Replay loader (day-by-day shard copies) + deterministic incident injectors |
| [dbt/](dbt/) | The dbt project: staging → intermediate → marts |
| [.claude/commands/](.claude/commands/) | Agent slash commands: spec-from-ticket, build-from-spec, triage-incident |
| [tickets/examples/](tickets/examples/) | Realistic stakeholder tickets driving the agent workflow |
