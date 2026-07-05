---
description: Turn a stakeholder ticket into a structured, costed spec — or a list of clarifying questions if the ticket is ambiguous.
argument-hint: <path to ticket, e.g. tickets/examples/ticket_001_extra_steps_d7_retention.md>
---

You are the analytics engineer on this repo. Produce a spec, not code.
CLAUDE.md is binding — especially the cost policy.

## Inputs

1. Read the ticket at `$ARGUMENTS`.
2. Read `docs/architecture.md` (event inventory, schema findings) and list
   the existing models (`dbt/models/**`) with their YAML docs — the spec
   must build on what exists, not duplicate it.

## Investigate (cheaply)

- Answer every data question with a real query: dev slice only
  (`_TABLE_SUFFIX`/`event_date` bounded), `--maximum_bytes_billed` on every
  call, dry-run anything unusual first. Record bytes scanned for each.
- Typical checks: does the event/param the ticket assumes actually exist?
  What are its values? Are populations large enough to be meaningful?

## Ambiguity rule (hard requirement)

If the ticket leaves a metric definition, population, comparison window, or
success criterion undefined — and the answer would change the model design —
**do not guess**. Write the spec through the "Business question" section,
then a numbered **Open questions** list phrased so the stakeholder can
answer each in one sentence, set frontmatter `status: needs-clarification`,
and stop. A wrong guess shipped confidently is worse than a question.

## Output

Write `specs/<ticket-file-stem>.md`:

```markdown
---
ticket: <path>
status: draft | needs-clarification   # a human flips draft -> approved
estimated_cost: <bytes scanned by the proposed model, from dry run>
---

# <Title>

## Business question       — one sentence, stakeholder language
## Proposed metrics        — exact grain, filters, edge cases, null semantics
## Sources                 — existing models/sources to build on
## Proposed model design   — model name(s) per CLAUDE.md naming, columns,
                             materialization, tests (PK + business invariant)
## Acceptance criteria     — checkable statements a reviewer can verify
## Verified during speccing — every recon query: what it showed, bytes scanned
## Open questions          — empty only if genuinely none
```

Do not write model SQL. Do not create branches or PRs. The spec is the
deliverable; a human approves it before /build-from-spec touches it.
