"""Data diff for modified marts between prod (analytics) and the PR's CI
build (dbt_ci): PK-set differences AND value differences for shared PKs.

The value diff is the important part — a PR can change a metric (retention_d7,
dau, funnel counts) while preserving every primary key, which a PK-only diff
would report as clean. For each PK present in both, we compare a hash of the
whole row and count the rows whose values moved.

Informational — it posts evidence for the human reviewer; it does not fail
the build. Every query carries maximum_bytes_billed.
"""

import argparse
import json
import sys
from pathlib import Path

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

PROJECT_ID = "data-eng-491120"
PROD_DATASET = "analytics"
CI_DATASET = "dbt_ci"
MAX_BYTES = 2_147_483_648  # 2 GiB, same as the ci profile cap


def primary_key(manifest: dict, model_unique_id: str) -> str | None:
    """The column under the model's `unique` test (CLAUDE.md: exactly one PK)."""
    for node in manifest["nodes"].values():
        if (
            node["resource_type"] == "test"
            and (node.get("test_metadata") or {}).get("name") == "unique"
            and model_unique_id in node["depends_on"]["nodes"]
        ):
            kwargs = node["test_metadata"].get("kwargs", {})
            if kwargs.get("column_name"):
                return kwargs["column_name"]
    return None


def scalar(client: bigquery.Client, sql: str) -> int:
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES)
    return next(iter(client.query(sql, job_config=job_config).result()))[0]


def changed_rows(client: bigquery.Client, prod: str, ci: str, pk: str) -> int:
    """Rows whose PK exists in both sides but whose values differ. Compares a
    hash of the whole row over the shared PK space (the PK is part of the
    hash but equal by construction, so only non-key changes register)."""
    sql = f"""
        with prod_fp as (
            select {pk} as _pk, farm_fingerprint(to_json_string(t)) as _fp
            from {prod} as t
        ),
        ci_fp as (
            select {pk} as _pk, farm_fingerprint(to_json_string(t)) as _fp
            from {ci} as t
        )
        select count(*)
        from prod_fp
        join ci_fp using (_pk)
        where prod_fp._fp != ci_fp._fp
    """
    return scalar(client, sql)


def diff_model(client: bigquery.Client, name: str, pk: str | None) -> list[str]:
    prod = f"`{PROJECT_ID}.{PROD_DATASET}.{name}`"
    ci = f"`{PROJECT_ID}.{CI_DATASET}.{name}`"
    try:
        prod_rows = scalar(client, f"select count(*) from {prod}")
    except NotFound:
        return [f"| `{name}` | new mart — no prod table to diff against | — | — | — | — |"]
    ci_rows = scalar(client, f"select count(*) from {ci}")
    if pk is None:
        return [f"| `{name}` | {prod_rows:,} | {ci_rows:,} | no unique test found | — | — |"]
    only_prod = scalar(
        client,
        f"select count(*) from (select {pk} from {prod} except distinct select {pk} from {ci})",
    )
    only_ci = scalar(
        client,
        f"select count(*) from (select {pk} from {ci} except distinct select {pk} from {prod})",
    )
    changed = changed_rows(client, prod, ci, pk)
    return [
        f"| `{name}` | {prod_rows:,} | {ci_rows:,} | {only_prod:,} | {only_ci:,} | {changed:,} |"
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-file", required=True)
    parser.add_argument("--manifest", default="dbt/target/manifest.json")
    parser.add_argument("--output", default="data_diff.md")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    models = [
        line.strip() for line in Path(args.models_file).read_text().splitlines() if line.strip()
    ]
    marts = []
    for node in manifest["nodes"].values():
        if (
            node["resource_type"] == "model"
            and node["name"] in models
            and "marts" in Path(node["path"]).parts
        ):
            marts.append((node["name"], primary_key(manifest, node["unique_id"])))

    lines = [
        "## Data diff — prod vs PR build (PK sets **and** values)",
        "",
        "| mart | prod rows | PR rows | PKs only in prod | PKs only in PR | rows changed |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    if not marts:
        lines.append("| _no modified marts_ | — | — | — | — | — |")
    else:
        client = bigquery.Client(project=PROJECT_ID)
        for name, pk in sorted(marts):
            lines.extend(diff_model(client, name, pk))
        lines += [
            "",
            "**rows changed** counts shared PKs whose values differ. It is "
            "non-zero when the PR intentionally changes a metric — but also "
            "when prod's full range and the CI dev-slice window legitimately "
            "produce different values for the same key (notably retention, "
            "whose horizon depends on how many days are loaded). The reviewer "
            "judges whether the change matches the PR's stated intent.",
        ]

    report = "\n".join(lines) + "\n"
    Path(args.output).write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
