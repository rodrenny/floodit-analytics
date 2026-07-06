"""Summarize the latest Elementary monitoring results as Markdown.

Reads the elementary_test_results table that Elementary's on-run-end hooks
maintain in <prod_dataset>_elementary. One capped query; output is the
per-run monitoring artifact attached to each replay workflow run.
"""

import argparse
import sys
from pathlib import Path

from google.api_core.exceptions import Forbidden, NotFound
from google.cloud import bigquery

PROJECT_ID = "data-eng-491120"
ELEMENTARY_DATASET = "analytics_elementary"
MAX_BYTES = 2_147_483_648  # 2 GiB

RESULTS_SQL = f"""
select
    detected_at,
    table_name,
    column_name,
    test_type,
    test_sub_type,
    status,
    test_results_description
from `{PROJECT_ID}.{ELEMENTARY_DATASET}.elementary_test_results`
where detected_at >= timestamp_sub(current_timestamp(), interval {{hours}} hour)
order by
    case status when 'fail' then 0 when 'warn' then 1 else 2 end,
    detected_at desc
limit 100
"""

STATUS_LABEL = {"pass": "pass", "warn": "**WARN**", "fail": "**FAIL**", "error": "**ERROR**"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=24, help="look-back window")
    parser.add_argument("--output", default="monitoring_report.md")
    args = parser.parse_args()

    client = bigquery.Client(project=PROJECT_ID)
    lines = [f"## Monitoring report — Elementary results, last {args.hours}h", ""]
    try:
        job_config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES)
        rows = list(client.query(RESULTS_SQL.format(hours=args.hours), job_config=job_config))
    except NotFound:
        lines.append("_No Elementary results dataset yet (first prod run pending)._")
        Path(args.output).write_text("\n".join(lines) + "\n")
        print("\n".join(lines))
        return 0
    except Forbidden as exc:
        # The report is informational; a permissions gap on the results
        # dataset must not fail the workflow (the build/freshness gates are
        # the real signal). Surface it clearly instead of crashing.
        lines.append(f"_Elementary results not accessible: {exc.message}_")
        Path(args.output).write_text("\n".join(lines) + "\n")
        print("\n".join(lines))
        return 0

    if not rows:
        lines.append("_No monitor results in the window._")
    else:
        alerts = sum(1 for row in rows if row["status"] in ("warn", "fail", "error"))
        lines += [
            f"{len(rows)} result(s), **{alerts} alerting**.",
            "",
            "| status | table | column | monitor | detail |",
            "|---|---|---|---|---|",
        ]
        for row in rows:
            detail = (row["test_results_description"] or "").replace("|", "\\|")[:160]
            lines.append(
                f"| {STATUS_LABEL.get(row['status'], row['status'])} "
                f"| `{row['table_name'] or '—'}` "
                f"| `{row['column_name'] or '—'}` "
                f"| {row['test_type']}/{row['test_sub_type'] or '—'} "
                f"| {detail} |"
            )

    report = "\n".join(lines) + "\n"
    Path(args.output).write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
