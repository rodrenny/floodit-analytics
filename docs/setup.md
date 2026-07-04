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

## Coming in later phases

- GitHub Actions secret configuration for BigQuery auth — Phase 3
- Branch protection settings (require CI green + 1 human review) — Phase 3
