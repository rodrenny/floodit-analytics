"""CI cost gate: dry-run the compiled SQL of every modified model and fail
the PR if any single model would scan more than COST_GATE_MAX_BYTES.

Dry runs are free — this gate spends nothing to enforce spending limits.
"""

import argparse
import os
import sys
from pathlib import Path

from google.cloud import bigquery

PROJECT_ID = "data-eng-491120"
DEFAULT_MAX_BYTES = 1_073_741_824  # 1 GiB


def find_compiled_sql(model_name: str, compiled_root: Path) -> Path | None:
    hits = sorted(compiled_root.rglob(f"{model_name}.sql"))
    return hits[0] if hits else None


def fmt_bytes(n: int) -> str:
    return f"{n / 1_048_576:,.1f} MiB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-file", required=True)
    parser.add_argument("--compiled-dir", default="dbt/target/compiled/floodit_analytics/models")
    parser.add_argument("--output", default="cost_gate.md")
    args = parser.parse_args()

    max_bytes = int(os.environ.get("COST_GATE_MAX_BYTES", DEFAULT_MAX_BYTES))
    models = [
        line.strip() for line in Path(args.models_file).read_text().splitlines() if line.strip()
    ]

    lines = [
        f"## Cost gate — dry run, limit {fmt_bytes(max_bytes)} per model",
        "",
        "| model | bytes scanned | status |",
        "|---|---:|---|",
    ]

    if not models:
        lines.append("| _no modified models_ | — | pass |")
        Path(args.output).write_text("\n".join(lines) + "\n")
        print("\n".join(lines))
        return 0

    client = bigquery.Client(project=PROJECT_ID)
    compiled_root = Path(args.compiled_dir)
    over_limit = []

    for name in models:
        sql_path = find_compiled_sql(name, compiled_root)
        if sql_path is None:
            lines.append(f"| `{name}` | no compiled SQL (skipped) | pass |")
            continue
        job_config = bigquery.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            maximum_bytes_billed=max_bytes,
        )
        job = client.query(sql_path.read_text(), job_config=job_config)
        scanned = job.total_bytes_processed or 0
        if scanned > max_bytes:
            over_limit.append(name)
            lines.append(f"| `{name}` | {fmt_bytes(scanned)} | **BLOCKED** |")
        else:
            lines.append(f"| `{name}` | {fmt_bytes(scanned)} | pass |")

    if over_limit:
        lines += [
            "",
            f"**Blocked:** {', '.join(f'`{m}`' for m in over_limit)} would scan "
            "more than the per-model CI limit. Tighten the partition/shard "
            "filter or ask a human to review the design — do not raise the cap.",
        ]

    report = "\n".join(lines) + "\n"
    Path(args.output).write_text(report)
    print(report)
    return 1 if over_limit else 0


if __name__ == "__main__":
    sys.exit(main())
