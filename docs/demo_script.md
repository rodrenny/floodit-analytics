# Demo script (3–4 minutes)

A live walkthrough of the self-driving analytics loop: an injected incident
becomes an alert, an agent triages it, and the whole thing is gated by
machines with a human at the merge button. Timings are a guide.

## Before you start (off-camera)

```sh
uv sync --all-groups
gcloud auth application-default login    # account owning data-eng-491120
cp dbt/profiles.yml.example dbt/profiles.yml
(cd dbt && uv run dbt deps)
uv run python -m loader.replay_loader --status   # confirm days are loaded
```

Have two things open: a terminal, and the repo's GitHub Actions tab.

## 0:00 — The thesis (20s)

> "Real GA4 telemetry — 114 days of Flood-It — replayed one day at a time.
> Agents draft; machines gate; I only review and merge. The rule that makes
> it safe: nothing runs without a byte cap, nothing merges without CI green
> plus my approval."

Show the [guardrail table in the README](../README.md#cost-guardrails--fail-closed-and-verified-by-tripping-them).

## 0:20 — Cost control is real, not aspirational (40s)

```sh
# Blocked by the per-query cap — bills nothing:
bq query --use_legacy_sql=false --maximum_bytes_billed=104857600 \
  "select count(distinct user_pseudo_id)
   from \`firebase-public-project.analytics_153293282.events_*\`
   where _table_suffix between '20180612' and '20181003'"

# Rejected by the table itself — no filter, no query:
bq query --use_legacy_sql=false --maximum_bytes_billed=1073741824 \
  "select count(*) from \`data-eng-491120.raw_floodit.events\`"
```

> "Two different layers, both fail-closed. One's the query cap, one's the
> table. Neither is an alert — they stop the query before it spends."

## 1:00 — Inject an incident (30s)

```sh
uv run python -m loader.incidents --null-spike platform 0.35
cd dbt && uv run dbt build --target prod 2>&1 | grep -E "WARN|monitor_"
```

> "I've corrupted one day — 35% of `platform` values nulled. The next prod
> build runs the monitors; `monitor_platform_null_rate` fires WARN. In a
> scheduled run this is the artifact the on-call sees."

## 1:30 — Triage it with an agent (60s)

In Claude Code: `/triage-incident`

> "The agent gathers evidence cheapest-first — all capped, all partition-
> filtered — pinpoints the day and column, matches the runbook signature,
> and walks the dbt lineage for blast radius."

Show the produced
[RCA report](../incidents/2026-07-05_platform_null_spike_report.md):
symptom, evidence table, root cause, affected models/exposures, fix.

## 2:30 — Recover, verified (30s)

```sh
uv run python -m loader.replay_loader --day 2018-07-11   # idempotent re-copy
cd dbt && uv run dbt build --target prod 2>&1 | grep Done  # 95 PASS / 0 WARN
```

> "One idempotent command restores the pristine shard. Monitor's green. No
> data was mutated in place — the day was re-copied from source."

## 3:00 — The gate that protects `main` (45s)

Open [PR #2](https://github.com/rodrenny/floodit-analytics/pull/2) and
[PR #9](https://github.com/rodrenny/floodit-analytics/pull/9) side by side.

> "Every model change is a PR. Here's one an agent built from an approved
> spec — cost gate 96.4 MiB, all green, I merged it. And here's one sized to
> scan 1.7 GiB — the cost gate blocked it, and branch protection made it
> unmergeable. Same pipeline, opposite outcomes, zero human judgment spent
> on either verdict."

## 3:45 — Close (15s)

> "Ticket to reviewed PR, incident to recovered pipeline — the agents do the
> drafting, the machines do the gating, and my attention goes only where
> judgment is actually required. That's the compression."

## Reset between runs

```sh
uv run python -m loader.replay_loader --day 2018-07-11   # ensure clean
uv run python -m loader.replay_loader --status
```
