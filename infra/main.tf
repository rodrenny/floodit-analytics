# Minimal by design: datasets, the raw events table, the CI service account,
# IAM bindings, and a budget alert. Everything else (models, loading,
# monitoring) lives outside Terraform. State is local and gitignored.

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

variable "project_id" {
  type    = string
  default = "data-eng-491120"
}

variable "location" {
  type    = string
  default = "US" # must stay colocated with firebase-public-project (US)
}

variable "billing_account_id" {
  type    = string
  default = "016B08-7B25A1-0CC280"
}

# 7 days, in ms. Applies to dev/CI datasets only — never raw or prod.
variable "dev_dataset_expiration_ms" {
  type    = number
  default = 604800000
}

provider "google" {
  project = var.project_id
  # The Billing Budgets API rejects user ADC without an explicit quota
  # project; this pair makes the provider send one.
  billing_project       = var.project_id
  user_project_override = true
}

data "google_project" "this" {}

locals {
  labels = {
    project = "floodit-analytics" # makes billing export filterable
  }
}

# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

resource "google_bigquery_dataset" "raw_floodit" {
  dataset_id  = "raw_floodit"
  location    = var.location
  labels      = local.labels
  description = "Raw GA4 events replayed day-by-day from the public Flood-It! export. Loaded by copy jobs only. No expiration."
}

resource "google_bigquery_dataset" "analytics" {
  dataset_id  = "analytics"
  location    = var.location
  labels      = local.labels
  description = "Production dbt output (marts). No expiration."
}

resource "google_bigquery_dataset" "dbt_dev" {
  dataset_id                 = "dbt_renny"
  location                   = var.location
  labels                     = local.labels
  default_table_expiration_ms = var.dev_dataset_expiration_ms
  description                = "Personal dev dataset for dbt. Tables expire after 7 days."
}

resource "google_bigquery_dataset" "dbt_ci" {
  dataset_id                 = "dbt_ci"
  location                   = var.location
  labels                     = local.labels
  default_table_expiration_ms = var.dev_dataset_expiration_ms
  description                = "Slim-CI build target for PR checks. Tables expire after 7 days."
}

# ---------------------------------------------------------------------------
# Raw events table
#
# Ingestion-time partitioned with a schema byte-identical to the public
# shards: that combination is what lets the loader use free copy jobs with
# the events$YYYYMMDD partition decorator. require_partition_filter makes
# BigQuery itself reject any unfiltered query, regardless of who wrote it.
# ---------------------------------------------------------------------------

resource "google_bigquery_table" "events" {
  dataset_id  = google_bigquery_dataset.raw_floodit.dataset_id
  table_id    = "events"
  description = "GA4 events, one ingestion-time partition per replayed day. Query via _PARTITIONDATE filters only."
  labels      = local.labels

  schema = file("${path.module}/events_schema.json")

  time_partitioning {
    type = "DAY"
  }

  require_partition_filter = true
  deletion_protection      = true
}

# ---------------------------------------------------------------------------
# CI service account — least privilege:
# job execution on the project, data access only on our four datasets.
# Read access to the public dataset needs no grant. No key is created here;
# CI auth is configured in Phase 3 (see docs/setup.md).
# ---------------------------------------------------------------------------

resource "google_service_account" "ci" {
  account_id   = "floodit-ci"
  display_name = "Flood-It analytics CI/CD"
}

resource "google_project_iam_member" "ci_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.ci.email}"
}

resource "google_bigquery_dataset_iam_member" "ci_data_editor" {
  for_each = {
    raw       = google_bigquery_dataset.raw_floodit.dataset_id
    analytics = google_bigquery_dataset.analytics.dataset_id
    dev       = google_bigquery_dataset.dbt_dev.dataset_id
    ci        = google_bigquery_dataset.dbt_ci.dataset_id
  }
  dataset_id = each.value
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.ci.email}"
}

# ---------------------------------------------------------------------------
# Budget alert — SOFT layer only: budgets notify, they never stop spend.
# The blocking layers are maximum_bytes_billed, require_partition_filter,
# and the manual 100 GiB/day project quota (docs/setup.md).
# ---------------------------------------------------------------------------

resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account_id
  display_name    = "floodit-analytics-monthly"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "EUR"
      units         = "5"
    }
  }

  threshold_rules {
    threshold_percent = 0.25
  }
  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 1.0
  }
}
