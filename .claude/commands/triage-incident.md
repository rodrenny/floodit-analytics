---
description: Investigate an active pipeline incident and produce an RCA report with blast radius and a proposed fix. Opens a draft PR only if the fix is code.
---

You are on call for this repo's replay pipeline. CLAUDE.md is binding —
every diagnostic query carries a byte cap and a partition/date filter.
Read `docs/runbooks/incident_triage.md` first: the injector → detector
mapping there resolves most incidents in this simulated pipeline.

## Gather evidence (in this order, cheapest first)

1. **Monitoring results**: query
   `analytics_elementary.elementary_test_results` for the last 48h
   (capped), or read the latest `monitoring-report` artifact from the
   `replay` workflow. Which monitors are warn/fail, on which table/column?
2. **Freshness**: `uv run dbt source freshness --target prod` — age vs the
   26h/50h thresholds.
3. **Loader state**: `uv run python -m loader.replay_loader --status`, plus
   recent `replay` workflow logs (look for `INCIDENT INJECTION` lines and
   copy-job errors). Partition metadata (`INFORMATION_SCHEMA.PARTITIONS`,
   capped) shows row counts per day — compare against the expected
   50,000/day.
4. **Recent changes**: `git log --oneline -15` and recently merged PRs —
   did code change when the symptom started?
5. **Blast radius**: from `dbt/target/manifest.json`, walk `child_map` from
   the affected model/source to the full downstream set, including
   exposures. Names, not hand-waving.

## Report

Write `incidents/<YYYY-MM-DD>_<slug>_report.md`:

```markdown
# Incident: <one-line symptom>
- **Detected**: <which monitor/gate fired, when, link/run id>
- **Status**: investigating | mitigated | resolved

## Symptom            — what alerted, exact numbers
## Evidence           — each finding with the query/command that produced it
## Root cause         — hypothesis + the evidence that confirms it
## Blast radius       — affected models/exposures from lineage, exact list
## Fix                — operational (runbook commands) or code (draft PR)
## Follow-ups         — what would have caught this sooner, if anything
```

## Fix rules

- Operational fixes (re-copy a day, resume the loader): give exact commands
  from the runbook; run them only if asked.
- Code fixes: draft branch + PR per CLAUDE.md, linked from the report.
  **Never merge. Never bypass CI.**
- If evidence is inconclusive, say so in the report — a wrong root cause
  asserted confidently is worse than an open investigation.
