# Setup

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Google Cloud SDK (`gcloud`, `bq`)
- Terraform >= 1.5 (needed from Phase 1; `brew install terraform`)
- GitHub CLI (`gh`) for the PR workflow (needed from Phase 3; `brew install gh`)

## GCP authentication

Everything targets project `data-eng-491120` in location `US`.

```sh
gcloud auth login                       # the account that owns data-eng-491120
gcloud auth application-default login   # ADC — used by dbt (method: oauth) and the Python loader
gcloud config set project data-eng-491120
```

Verify: `gcloud auth application-default print-access-token >/dev/null && echo OK`.

No key files are used locally, ever. CI authenticates with a dedicated
service account via a GitHub secret (see CI section, Phase 3).

## Local environment

```sh
uv sync --all-groups        # installs dbt, ruff, sqlfluff, pre-commit, pytest
uv run pre-commit install   # enables the git hooks
cp dbt/profiles.yml.example dbt/profiles.yml
```

`dbt/profiles.yml` is gitignored. Every target in it carries
`maximum_bytes_billed` (2 GiB dev/ci, 10 GiB prod) — do not remove or raise
these caps; a query that legitimately needs more is a design conversation,
not a config edit.

## Cost backstop: project-level daily query quota (manual, do this once)

Budgets notify; **quotas block**. This quota is the layer that survives a
misconfigured profile or a runaway agent loop:

1. Console → **IAM & Admin → Quotas & System Limits**
2. Filter service = *BigQuery API*, metric = **Query usage per day**
3. Select the row, **Edit quota**, set to **100 GiB/day**, submit.

Document owner note: budget alerts (Terraform, Phase 1) are a soft layer on
top — they do **not** stop spend.

## Infrastructure (Terraform)

Terraform manages datasets, the raw events table, the CI service account,
IAM bindings, and the budget alert — nothing else. State is local and
gitignored.

```sh
brew install hashicorp/tap/terraform   # core homebrew formula is gone (BSL relicensing)
cd infra
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Required APIs (`gcloud services enable ...`): `bigquery.googleapis.com`,
`cloudresourcemanager.googleapis.com`, `iam.googleapis.com`,
`billingbudgets.googleapis.com`. The provider sets
`user_project_override = true` because the Billing Budgets API rejects user
ADC without an explicit quota project.

The raw table `raw_floodit.events` has `deletion_protection = true`; if you
genuinely need to destroy it, that flag is a deliberate two-step.

## Replay loader

The loader copies one public shard per run into the matching partition of
`raw_floodit.events` — copy jobs only, so every run is free and idempotent
(`WRITE_TRUNCATE` per partition). Replay state (one row: simulation start,
next shard) lives in `raw_floodit.replay_state`, written via load jobs and
read via `tabledata.list` — the loader contains no query job at all.

```sh
uv run python -m loader.replay_loader --reset        # initialize at 2018-06-12
uv run python -m loader.replay_loader                # load the next day
uv run python -m loader.replay_loader --catch-up 5   # load the next 6 days
uv run python -m loader.replay_loader --day 2018-06-15  # re-copy one day, state untouched
uv run python -m loader.replay_loader --status
```

In production the daily `replay.yml` workflow runs loader → `dbt build`
(prod) → `dbt source freshness`. Freshness on `raw_floodit.events` is
metadata-based (table last-modified — free to check): `warn_after: 26h`,
`error_after: 50h` of wall-clock time since the last copy job.

## GitHub Actions → BigQuery auth (Workload Identity Federation, no keys)

All workflows authenticate via WIF; no JSON key exists at any point. Two
repository secrets:

| Secret | Value |
|---|---|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/961154607867/locations/global/workloadIdentityPools/github/providers/github-oidc` |
| `GCP_CI_SERVICE_ACCOUNT` | `floodit-ci@data-eng-491120.iam.gserviceaccount.com` |

The pool (`github`) and OIDC provider (`github-oidc`, attribute-condition
locked to `rodrenny/floodit-analytics`) already exist. **One manual step
remains — an IAM grant the repo owner must run themselves:**

```sh
gcloud iam service-accounts add-iam-policy-binding \
    floodit-ci@data-eng-491120.iam.gserviceaccount.com \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/projects/961154607867/locations/global/workloadIdentityPools/github/attribute.repository/rodrenny/floodit-analytics"
```

## CI gates (every PR, fail-fast)

`ci.yml` runs, in order: **lint** (ruff + SQLFluff) → **slim build**
(`state:modified+` with `--defer` against the manifest artifact published
from `main` by `manifest.yml`; full build if no artifact yet) → **contract
guard** (every mart `contract: enforced`) → **cost gate** (free dry run per
modified model, fails > 1 GiB, posts a per-model bytes table on the PR) →
**data diff** (row counts + PK-level `except distinct` vs prod for modified
marts, posted on the PR; informational).

## Branch protection (set once in repo settings)

On `main`: require status checks `lint`, `build`, `cost_gate`, `data_diff`
to pass; require the branch to be up to date; require 1 approving review;
no force pushes; no direct pushes for admins. **Agents open PRs; humans
merge — no exceptions.** Note for a single-owner repo: GitHub does not let
a PR author approve their own PR, so the review requirement documents the
intended team posture; the enforceable subset (status checks) should always
be on.
