"""Deterministic incident injection for the replay pipeline.

Each injector produces exactly one class of failure so the monitoring layer
(and the triage agent) can be exercised on demand:

  --skip-day            next scheduled run loads nothing -> freshness breach
  --duplicate-day       re-append the last day's shard   -> volume anomaly
  --drop-column COL     null out COL for the last day    -> null-rate anomaly
  --null-spike COL PCT  null PCT of COL for the last day -> quality regression

skip-day and duplicate-day stay free (state write / copy job). drop-column
and null-spike are THE documented exception to the copy-jobs-only rule
(CLAUDE.md cost policy): they rewrite one day with a query-based load,
always with maximum_bytes_billed set and the partition filter applied.

Recovery for any rewritten/duplicated day:
    uv run python -m loader.replay_loader --day <YYYY-MM-DD>
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from google.cloud import bigquery

from loader.replay_loader import (
    PROJECT_ID,
    RAW_DATASET,
    RAW_TABLE,
    copy_shard_append,
    partition_info,
    partition_table,
    read_state,
    write_state,
)

MAX_BYTES = 2_147_483_648  # 2 GiB — same cap as the dev/ci profile

logger = logging.getLogger("incidents")


def last_loaded_day(client: bigquery.Client) -> date:
    state = read_state(client)
    if state is None or state.next_shard_date == state.simulation_start_date:
        raise SystemExit("No loaded days found — run the replay loader first.")
    return state.next_shard_date - timedelta(days=1)


def inject_skip_day(client: bigquery.Client, runs: int = 1) -> None:
    state = read_state(client)
    if state is None:
        raise SystemExit("No replay state — initialize the loader first.")
    state.skip_runs += runs
    write_state(client, state)
    logger.info(
        "Injected skip-day: the next %d loader run(s) will load nothing "
        "(freshness ages past warn at 26h, error at 50h).",
        state.skip_runs,
    )


def inject_duplicate_day(client: bigquery.Client, day: date) -> None:
    before_rows, _ = partition_info(client, day)
    copy_shard_append(client, day)
    after_rows, _ = partition_info(client, day)
    logger.info(
        "Injected duplicate-day on %s: %s -> %s rows (volume anomaly).",
        day.isoformat(),
        f"{before_rows:,}",
        f"{after_rows:,}",
    )


def build_rewrite_sql(
    schema: list[bigquery.SchemaField], column: str, day: date, pct: float
) -> str:
    """SELECT that reproduces the partition with `column` nulled for pct of
    rows (pct=1.0 drops it entirely). Only top-level columns are supported —
    that covers every injectable field (platform, user_pseudo_id, ...)."""
    fields = {field.name: field for field in schema}
    if column not in fields:
        raise SystemExit(f"Column {column!r} is not a top-level column of {RAW_TABLE}.")
    select_list = []
    for name, field in fields.items():
        if name == column:
            if pct >= 1.0:
                select_list.append(f"cast(null as {field.field_type}) as {name}")
            else:
                select_list.append(f"if(rand() < {pct}, null, {name}) as {name}")
        else:
            select_list.append(name)
    columns = ",\n    ".join(select_list)
    return (
        f"select\n    {columns}\n"
        f"from `{PROJECT_ID}.{RAW_DATASET}.{RAW_TABLE}`\n"
        f"where _partitiondate = '{day.isoformat()}'"
    )


def inject_column_incident(client: bigquery.Client, column: str, pct: float, day: date) -> None:
    """Rewrite one day's partition with a column (partially) nulled.

    Documented cost-policy exception: a query-based load of a single day,
    capped and partition-filtered.
    """
    table = client.get_table(f"{PROJECT_ID}.{RAW_DATASET}.{RAW_TABLE}")
    sql = build_rewrite_sql(table.schema, column, day, pct)
    job_config = bigquery.QueryJobConfig(
        destination=partition_table(day),
        maximum_bytes_billed=MAX_BYTES,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        use_legacy_sql=False,
    )
    job = client.query(sql, job_config=job_config)
    job.result()
    num_rows, _ = partition_info(client, day)
    label = "drop-column" if pct >= 1.0 else f"null-spike {pct:.0%}"
    logger.info(
        "Injected %s on %s.%s for %s (%s rows rewritten, %s bytes billed).",
        label,
        RAW_TABLE,
        column,
        day.isoformat(),
        f"{num_rows:,}",
        f"{job.total_bytes_billed or 0:,}",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--skip-day", action="store_true", help="next loader run loads nothing")
    group.add_argument("--duplicate-day", action="store_true", help="re-append the last day")
    group.add_argument("--drop-column", metavar="COL", help="null out COL for the last day")
    group.add_argument(
        "--null-spike",
        nargs=2,
        metavar=("COL", "PCT"),
        help="null PCT (0..1) of COL for the last day",
    )
    parser.add_argument(
        "--day",
        type=date.fromisoformat,
        help="target day (default: last loaded day; ignored by --skip-day)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    client = bigquery.Client(project=PROJECT_ID)
    if args.skip_day:
        inject_skip_day(client)
        return
    day = args.day or last_loaded_day(client)
    if args.duplicate_day:
        inject_duplicate_day(client, day)
    elif args.drop_column:
        inject_column_incident(client, args.drop_column, 1.0, day)
    elif args.null_spike:
        column, pct = args.null_spike[0], float(args.null_spike[1])
        if not 0 < pct <= 1:
            raise SystemExit("PCT must be in (0, 1].")
        inject_column_incident(client, column, pct, day)


if __name__ == "__main__":
    sys.exit(main())
