"""Day-by-day replay of the public Flood-It! GA4 shards into raw_floodit.events.

Each run copies the next public daily shard into the matching ingestion-time
partition (events$YYYYMMDD, WRITE_TRUNCATE), so the raw table grows one day
per run as if 2018 were happening now.

Free operations only: data moves via copy jobs, state is written via load
jobs and read via tabledata.list. No query job exists in this module — that
is a cost-policy invariant, not an implementation detail (see CLAUDE.md).
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

PROJECT_ID = "data-eng-491120"
RAW_DATASET = "raw_floodit"
RAW_TABLE = "events"
STATE_TABLE = "replay_state"

PUBLIC_PROJECT = "firebase-public-project"
PUBLIC_DATASET = "analytics_153293282"

# Verified available shard range (see docs/architecture.md).
FIRST_SHARD_DATE = date(2018, 6, 12)
LAST_SHARD_DATE = date(2018, 10, 3)

STATE_SCHEMA = [
    bigquery.SchemaField("simulation_start_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("next_shard_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
    # Incident injection (see loader/incidents.py --skip-day): while > 0,
    # each run decrements and loads nothing, simulating a stalled pipeline.
    bigquery.SchemaField("skip_runs", "INTEGER", mode="NULLABLE"),
]

logger = logging.getLogger("replay_loader")


@dataclass
class ReplayState:
    simulation_start_date: date
    next_shard_date: date
    skip_runs: int = 0


def shard_table(day: date) -> str:
    return f"{PUBLIC_PROJECT}.{PUBLIC_DATASET}.events_{day:%Y%m%d}"


def partition_table(day: date) -> str:
    return f"{PROJECT_ID}.{RAW_DATASET}.{RAW_TABLE}${day:%Y%m%d}"


def state_table() -> str:
    return f"{PROJECT_ID}.{RAW_DATASET}.{STATE_TABLE}"


def days_to_load(state: ReplayState, catch_up: int) -> list[date]:
    """The next 1 + catch_up shard dates, clamped to the available range."""
    days = []
    day = state.next_shard_date
    for _ in range(1 + catch_up):
        if day > LAST_SHARD_DATE:
            break
        days.append(day)
        day += timedelta(days=1)
    return days


def advance(state: ReplayState, loaded_through: date) -> ReplayState:
    return ReplayState(
        simulation_start_date=state.simulation_start_date,
        next_shard_date=loaded_through + timedelta(days=1),
        skip_runs=state.skip_runs,
    )


def state_to_row(state: ReplayState) -> dict:
    return {
        "simulation_start_date": state.simulation_start_date.isoformat(),
        "next_shard_date": state.next_shard_date.isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "skip_runs": state.skip_runs,
    }


def read_state(client: bigquery.Client) -> ReplayState | None:
    """Read the single state row via tabledata.list (free — not a query)."""
    try:
        rows = list(client.list_rows(state_table(), max_results=1))
    except NotFound:
        return None
    if not rows:
        return None
    row = rows[0]
    return ReplayState(
        simulation_start_date=row["simulation_start_date"],
        next_shard_date=row["next_shard_date"],
        skip_runs=row.get("skip_runs") or 0,
    )


def write_state(client: bigquery.Client, state: ReplayState) -> None:
    """Overwrite the single state row via a load job (free — not a query)."""
    job_config = bigquery.LoadJobConfig(
        schema=STATE_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        # WRITE_TRUNCATE replaces the table schema wholesale, so adding
        # columns (e.g. skip_runs) needs no schema_update_options.
    )
    job = client.load_table_from_json([state_to_row(state)], state_table(), job_config=job_config)
    job.result()


def copy_shard(client: bigquery.Client, day: date) -> None:
    """Copy one public shard into its partition. WRITE_TRUNCATE on the
    partition decorator makes re-runs idempotent."""
    job_config = bigquery.CopyJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    client.copy_table(shard_table(day), partition_table(day), job_config=job_config).result()


def copy_shard_append(client: bigquery.Client, day: date) -> None:
    """Append a shard onto its partition — only used by the duplicate-day
    incident injector. Still a free copy job."""
    job_config = bigquery.CopyJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    client.copy_table(shard_table(day), partition_table(day), job_config=job_config).result()


def partition_info(client: bigquery.Client, day: date) -> tuple[int, int]:
    """(num_rows, num_bytes) of one partition, via table metadata (free)."""
    table = client.get_table(partition_table(day))
    return table.num_rows, table.num_bytes


def run_replay(client: bigquery.Client, catch_up: int = 0) -> list[date]:
    state = read_state(client)
    if state is None:
        raise SystemExit("No replay state found — initialize with --reset first.")
    if state.skip_runs > 0:
        logger.warning(
            "INCIDENT INJECTION: skipping this run (%d skip(s) remaining); nothing loaded.",
            state.skip_runs - 1,
        )
        state.skip_runs -= 1
        write_state(client, state)
        return []
    days = days_to_load(state, catch_up)
    if not days:
        logger.info(
            "Replay complete: all shards through %s are loaded.", LAST_SHARD_DATE.isoformat()
        )
        return []
    for day in days:
        copy_shard(client, day)
        num_rows, num_bytes = partition_info(client, day)
        logger.info(
            "Loaded %s -> %s (%s rows, %s bytes)",
            shard_table(day),
            partition_table(day),
            f"{num_rows:,}",
            f"{num_bytes:,}",
        )
    write_state(client, advance(state, days[-1]))
    return days


def reset_state(client: bigquery.Client, start_date: date) -> None:
    table = bigquery.Table(state_table(), schema=STATE_SCHEMA)
    try:
        client.create_table(table)
        logger.info("Created state table %s", state_table())
    except Exception as exc:  # noqa: BLE001 — already-exists is fine
        if "Already Exists" not in str(exc):
            raise
    write_state(
        client,
        ReplayState(simulation_start_date=start_date, next_shard_date=start_date),
    )
    logger.info("State reset: replay will start at %s", start_date.isoformat())


def reload_day(client: bigquery.Client, day: date) -> None:
    """Re-copy a single day without touching state (idempotent repair path)."""
    if not FIRST_SHARD_DATE <= day <= LAST_SHARD_DATE:
        raise SystemExit(
            f"{day} is outside the available shard range ({FIRST_SHARD_DATE} .. {LAST_SHARD_DATE})."
        )
    copy_shard(client, day)
    num_rows, num_bytes = partition_info(client, day)
    logger.info(
        "Reloaded %s (%s rows, %s bytes); state untouched.",
        partition_table(day),
        f"{num_rows:,}",
        f"{num_bytes:,}",
    )


def show_status(client: bigquery.Client) -> None:
    state = read_state(client)
    if state is None:
        logger.info("No state — run --reset to initialize.")
        return
    loaded_days = (state.next_shard_date - state.simulation_start_date).days
    logger.info(
        "Simulation started at %s; next shard to load: %s; %d day(s) loaded.",
        state.simulation_start_date.isoformat(),
        state.next_shard_date.isoformat(),
        loaded_days,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catch-up",
        type=int,
        default=0,
        metavar="N",
        help="load N additional days beyond the next one",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="(re)initialize replay state; combine with --start-date",
    )
    parser.add_argument(
        "--start-date",
        type=date.fromisoformat,
        default=FIRST_SHARD_DATE,
        help="simulation start date for --reset (default: first available shard)",
    )
    parser.add_argument(
        "--day",
        type=date.fromisoformat,
        help="re-copy one specific day without advancing state",
    )
    parser.add_argument("--status", action="store_true", help="print state and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    client = bigquery.Client(project=PROJECT_ID)
    if args.status:
        show_status(client)
    elif args.reset:
        reset_state(client, args.start_date)
    elif args.day:
        reload_day(client, args.day)
    else:
        run_replay(client, catch_up=args.catch_up)


if __name__ == "__main__":
    sys.exit(main())
