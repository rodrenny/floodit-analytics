---
ticket: tickets/examples/ticket_001_extra_steps_d7_retention.md
status: approved # human sign-off: rodrenny, 2026-07-05
estimated_cost: 425138237 # bytes, dry run of the model-shaped join at prod scale (~405 MiB)
---

# D1/D7/D30 retention by extra-steps starting grant

## Business question

Do new players who receive a larger extra-steps starting grant retain
better at day 7 (D1 and D30 alongside for context)?

## Proposed metrics

- **Grain:** one row per starting-grant bucket.
- **Buckets:** verified to cluster into exactly four values — `3`, `5`,
  `10`, `20` — plus users with no observed grant, shown as `unassigned`
  (never hidden; the ticket asked for honesty about small buckets).
- **Population:** users with `has_observed_first_open = true` (install
  observed inside the loaded window). Pre-window installs are excluded —
  their cohort day, and usually their grant, is unobserved.
- **Retention day N:** user active exactly N days after their first_open
  date (classic day-N, consistent with `retention_cohorts`).
- **Null semantics / observability:** each day-N rate uses its own
  denominator — only cohort members whose day N falls inside the loaded
  window (`cohort_date + N <= max loaded date`). Rates are null when the
  denominator is 0. This keeps buckets comparable while the replay is
  mid-window and prevents unobservable horizons reading as churn.
- **Edge case:** the grant is the user's *latest observed* value of the
  `initial_extra_steps` user property (via `dim_users`); if a user's grant
  was changed mid-life, they count under the latest one. Documented on the
  mart, acceptable for the board question.

## Sources

- `dim_users` (grant bucket, cohort membership, first_open date)
- `int_user_days` (activity spine for day-N checks)

No new staging or intermediate work needed.

## Proposed model design

`retention_by_extra_steps_grant` in `models/marts/engagement/` —
table, `contract: enforced`, columns:

| column | type | notes |
|---|---|---|
| `grant_bucket` | string | PK: '3', '5', '10', '20', 'unassigned' |
| `cohort_users` | int64 | users with observed first_open in the bucket |
| `d1_denominator` / `d7_denominator` / `d30_denominator` | int64 | observable-horizon members |
| `retained_d1` / `retained_d7` / `retained_d30` | int64 | |
| `retention_d1` / `retention_d7` / `retention_d30` | float64 | null when denominator 0 |

Tests: `unique` + `not_null` on `grant_bucket`; business invariants:
each rate null or in [0,1]; each denominator ≤ `cohort_users`; each
`retained_dN` ≤ its denominator.

## Acceptance criteria

- One row per bucket, including `unassigned`; no bucket dropped.
- Rates null (not 0) wherever the horizon denominator is 0.
- `dbt build --select +retention_by_extra_steps_grant` green on the dev
  slice with all tests; compiled model dry-runs under the 1 GiB CI gate.
- Column docs state the latest-observed-grant caveat.

## Verified during speccing (all queries capped)

| Check | Result | Bytes |
|---|---|---|
| Grant distribution (`dim_users`, dev slice) | Exactly 4 buckets {3,5,10,20} + null; cohort users per bucket 37–51 on 7 days | 33 KB |
| D1 by bucket, model-shaped join (dev slice) | Join works; D1 8.1–18.9% (noisy at slice size — full-range aggregation is the point of the mart) | 3.4 MB |
| Model-shaped join, prod scale (dry run) | **425,138,237 bytes (~405 MiB)** — under the 1 GiB CI cost gate | 0 (dry run) |

## Open questions

None — the ticket's one stated unknown (bucket clustering) was resolved by
data: the grants form four clean buckets, so no binning decision is needed.
