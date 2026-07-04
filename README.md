# floodit-analytics

An analytics engineering repository over real mobile-game telemetry — the
public [Flood-It!](https://play.google.com/store/apps/details?id=com.labpixies.flood)
GA4 export (`firebase-public-project.analytics_153293282.events_*`, 114
daily-sharded tables, ~5.7M nested events) — built to demonstrate an
AI-amplified analytics workflow: agents draft the models, tests, docs, and
incident reports; layered machine gates (linting, contracts, cost caps,
data diffs) do the blocking; a human reviews and merges.

> **Status: under construction.** Phase 0 (conventions & scaffolding) is
> done. Architecture diagram, guardrail inventory, and verified metrics
> land as their phases complete — every number in this README will come
> from a query or run that actually happened, and nothing will be written
> here before it does.

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
