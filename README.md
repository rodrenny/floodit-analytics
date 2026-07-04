# floodit-analytics

An analytics engineering repository over real mobile-game telemetry — the
public [Flood-It!](https://play.google.com/store/apps/details?id=com.labpixies.flood)
GA4 export (`firebase-public-project.analytics_153293282.events_*`, 114
daily-sharded tables, ~5.7M nested events) — built to demonstrate an
AI-amplified analytics workflow: agents draft the models, tests, docs, and
incident reports; layered machine gates (linting, contracts, cost caps,
data diffs) do the blocking; a human reviews and merges.

> **Status: under construction.** Phases 0 (conventions & scaffolding) and
> 1 (infra + dbt foundation) are done. Every number in this README comes
> from a query or run that actually happened, and nothing is written here
> before it does.

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
