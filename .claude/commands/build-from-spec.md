---
description: Implement an approved spec — models, tests, docs — verify on the dev slice, and open a PR. Never merges.
argument-hint: <path to approved spec, e.g. specs/ticket_001_extra_steps_d7_retention.md>
---

You are the analytics engineer on this repo. CLAUDE.md is binding.

## Preconditions (check, don't assume)

1. Read the spec at `$ARGUMENTS`. Its frontmatter must say
   `status: approved`. If it doesn't — stop and say so. Building from an
   unapproved spec is a policy violation, not initiative.
2. Re-read the referenced sources/models; if the repo has drifted since the
   spec was written (renamed columns, changed grains), stop and flag it.

## Implement

- Branch from latest `main`: `feat/<spec-stem>`.
- Follow the spec exactly; follow CLAUDE.md for everything the spec leaves
  open (naming, CTE style, one concern per CTE, no `SELECT *` outside
  staging/import CTEs).
- Marts: `contract: enforced`, explicit `data_type` on every column, every
  column documented, `unique` + `not_null` on the PK, at least one
  business-invariant test. Update `_<dir>__models.yml` next to the model.
- Prefer building on existing intermediates over re-deriving logic.

## Verify (all of it, locally, before the PR)

1. `uv run sqlfluff lint` on the new files — clean.
2. `uv run dbt build --select +<model>` on the dev target — green; capture
   the output.
3. Dry-run the compiled model SQL with a byte cap — must be under the
   1 GiB CI cost gate; record the bytes.

## Deliver

- Conventional commits; push; `gh pr create` with: what/why, the spec
  linked, the `dbt build` output, and the dry-run bytes. State expected CI
  behavior.
- **Never merge, never push to main, never bypass CI.** The PR link is the
  deliverable. If CI fails, fix and push; if a gate blocks for a reason the
  spec didn't anticipate, comment on the PR and stop.
