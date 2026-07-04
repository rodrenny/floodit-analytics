# CLAUDE.md — Engineering Conventions

This file is the contract for every agent and human working in this repo.
PRs that violate it get rejected in review. If a rule here conflicts with
convenience, the rule wins. If a rule is genuinely wrong, change the rule
in its own PR — do not silently deviate.

## Project context

Analytics engineering repo over the public Flood-It! GA4 export
(`firebase-public-project.analytics_153293282.events_*`), replayed
day-by-day into `data-eng-491120.raw_floodit.events` and modeled with dbt
into `analytics` (prod) / `dbt_renny` (dev). CI is the gatekeeper; agents
draft, humans merge.

## Cost policy (read this first — it overrides everything else)

- **Every query carries a byte cap.** dbt targets set `maximum_bytes_billed`
  (2 GiB dev/ci, 10 GiB prod). Ad-hoc queries via `bq` use
  `--maximum_bytes_billed`; Python uses `QueryJobConfig(maximum_bytes_billed=...)`.
  A query path without a cap is a bug. If a legitimate query needs more than
  the cap, stop and ask a human — never raise the cap yourself.
- **Every query filters the partition/shard.** The raw table has
  `require_partition_filter = true`; BigQuery rejects unfiltered queries.
  Queries against the public dataset must bound `_TABLE_SUFFIX`.
  All dbt models must propagate a filter on `event_date`.
- **Develop against the 7-day dev slice**, never the full range. The slice
  bounds live in dbt vars; don't hardcode dates in models.
- **Dry-run before anything unusual.** Anything projected to scan > 5 GiB:
  stop and ask.
- **Free operations stay free.** The loader uses copy jobs only. The CI cost
  gate uses dry runs only. Do not replace either with a query-based
  alternative. (Single documented exception: `loader/incidents.py`
  injectors that must rewrite a day may query-load one day, capped and
  partition-filtered.)
- **Prefer incremental models** wherever the grain is daily and late-arriving
  data doesn't force full rebuilds.

## Naming conventions

### Models
- `stg_<source>__<entity>` — staging, e.g. `stg_floodit__events`.
  1:1 with a source entity; rename, cast, flatten. No joins, no business logic.
- `int_<entity>_<verb-phrase>` — intermediate, e.g. `int_events_sessionized`,
  `int_user_days`. Not exposed to consumers; not queried by BI.
- `fct_<entity>` / `dim_<entity>` — core marts, e.g. `fct_events`, `dim_users`.
- Other marts are named for the business question in plain words:
  `daily_active_users`, `retention_cohorts`, `level_funnel_daily`.
  A stakeholder should understand the table from its name alone.

### Columns
- `snake_case`, always.
- Timestamps end in `_at` (UTC); dates end in `_date`.
- Booleans start with `is_` or `has_`.
- Primary/foreign keys: `<entity>_id` (e.g. `user_id`, `session_id`).
  Every model declares exactly one primary key (surrogate via
  `dbt_utils.generate_surrogate_key` when no natural key exists).
- No abbreviations that save fewer than 4 characters (`num_events`, not `n_ev`).

### Files
- One model per file; file name == model name.
- YAML docs/tests live in `_<dir>__models.yml` next to the models
  (e.g. `models/staging/_staging__models.yml`).

## SQL style

- CTEs over subqueries, always.
- Import CTEs first: every `ref`/`source` is selected into a named CTE at
  the top before any transformation.
- One transformation concern per CTE, named for what it does
  (`sessions_numbered`, `daily_rollup`) — not `cte1`, `tmp`.
- `SELECT *` is allowed only in staging models and import CTEs.
  Marts and intermediates list every column.
- Explicit column lists in `GROUP BY` (numbers acceptable only in ad-hoc
  work, never in committed models).
- Keywords lowercase; four-space indent; trailing commas per SQLFluff config.
- `{{ ref() }}` / `{{ source() }}` only — never a hardcoded table path
  in a model.
- Shared logic becomes a macro once used twice (e.g. `extract_param`).

## Testing policy

- **Every model**: `unique` + `not_null` on its primary key. No exceptions.
- **Every mart**: at least one business-logic test beyond the PK tests —
  a singular test or expression test asserting an invariant of the metric
  (e.g. "retention_d7 between 0 and 1", "funnel step counts monotonically
  decrease").
- Source freshness is configured on the raw source and must stay green.
- A model without tests does not merge.

## Documentation policy

- Every model has a `description`. Every mart column has a `description`.
- Staging columns may inherit descriptions via doc blocks; marts may reuse
  doc blocks but must not leave columns undocumented.
- Metric definitions (grain, filters, edge cases) are documented on the
  mart, not in tribal knowledge or PR comments.
- Update docs in the same PR as the code they describe — never "later".

## Contracts

- All marts set `contract: enforced` with explicit column data types.
- Changing a mart's public interface (column added/removed/retyped) is a
  design decision: flag it in the PR description and get explicit human
  sign-off.

## PR & commit policy

- **Agents open PRs; humans merge. No exceptions.** No agent may merge,
  push to `main`, force-push, or bypass CI under any circumstances.
- Conventional commits: `feat:`, `fix:`, `docs:`, `ci:`, `chore:`, `test:`,
  `refactor:`. Small commits; each leaves the repo in a working state.
- Every PR: CI green + 1 human review before merge.
- Claims in PRs must be verified: if the PR says "tested", the PR shows the
  `dbt build` output. "Should work" is not done.

## Approved stack

BigQuery, dbt-core + dbt-bigquery, Python 3.11+ managed with `uv`, `ruff`,
SQLFluff (BigQuery dialect, dbt templater), GitHub Actions, Terraform
(datasets/SA/IAM only), Elementary. Anything else: ask before adding.
