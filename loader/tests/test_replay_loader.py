"""Unit tests for replay state logic and idempotency guarantees.

BigQuery interactions are faked; these tests cover the pure sequencing/state
logic and the free-operations invariant that run_replay never issues a query.
"""

from datetime import date

import pytest

from loader import replay_loader
from loader.replay_loader import (
    FIRST_SHARD_DATE,
    LAST_SHARD_DATE,
    ReplayState,
    advance,
    days_to_load,
    partition_table,
    shard_table,
    state_to_row,
)


def state(next_day: date) -> ReplayState:
    return ReplayState(simulation_start_date=FIRST_SHARD_DATE, next_shard_date=next_day)


class TestDaysToLoad:
    def test_default_run_loads_exactly_one_day(self):
        assert days_to_load(state(date(2018, 7, 1)), catch_up=0) == [date(2018, 7, 1)]

    def test_catch_up_loads_consecutive_days(self):
        assert days_to_load(state(date(2018, 7, 1)), catch_up=2) == [
            date(2018, 7, 1),
            date(2018, 7, 2),
            date(2018, 7, 3),
        ]

    def test_clamps_at_last_available_shard(self):
        assert days_to_load(state(LAST_SHARD_DATE), catch_up=10) == [LAST_SHARD_DATE]

    def test_empty_when_replay_is_complete(self):
        assert days_to_load(state(LAST_SHARD_DATE + (date(2018, 10, 4) - LAST_SHARD_DATE)), 5) == []


class TestAdvance:
    def test_advances_to_day_after_last_loaded(self):
        new = advance(state(date(2018, 7, 1)), loaded_through=date(2018, 7, 3))
        assert new.next_shard_date == date(2018, 7, 4)

    def test_preserves_simulation_start(self):
        new = advance(state(date(2018, 7, 1)), loaded_through=date(2018, 7, 1))
        assert new.simulation_start_date == FIRST_SHARD_DATE


class TestNaming:
    def test_shard_table(self):
        assert (
            shard_table(date(2018, 6, 12))
            == "firebase-public-project.analytics_153293282.events_20180612"
        )

    def test_partition_decorator(self):
        assert partition_table(date(2018, 6, 12)) == ("data-eng-491120.raw_floodit.events$20180612")


class TestStateSerialization:
    def test_round_trip_fields(self):
        row = state_to_row(state(date(2018, 7, 5)))
        assert row["simulation_start_date"] == "2018-06-12"
        assert row["next_shard_date"] == "2018-07-05"
        assert "updated_at" in row


class FakeClient:
    """Duck-typed stand-in recording every BigQuery operation."""

    def __init__(self, next_shard_date: date):
        self._state = state(next_shard_date)
        self.copied: list[tuple[str, str]] = []
        self.state_writes: list[dict] = []

    # -- free operations the loader is allowed to use -----------------
    def list_rows(self, table, max_results=None):
        return [
            {
                "simulation_start_date": self._state.simulation_start_date,
                "next_shard_date": self._state.next_shard_date,
            }
        ]

    def copy_table(self, source, dest, job_config=None):
        self.copied.append((source, dest))
        return _DoneJob()

    def load_table_from_json(self, rows, table, job_config=None):
        self.state_writes.extend(rows)
        return _DoneJob()

    def get_table(self, table):
        class _T:
            num_rows = 50_000
            num_bytes = 35_000_000

        return _T()

    def __getattr__(self, name):
        raise AssertionError(f"loader called forbidden client method: {name}")


class _DoneJob:
    def result(self):
        return self


class TestRunReplay:
    def test_loads_next_day_and_advances_state(self):
        client = FakeClient(next_shard_date=date(2018, 7, 1))
        loaded = replay_loader.run_replay(client)
        assert loaded == [date(2018, 7, 1)]
        assert client.copied == [(shard_table(date(2018, 7, 1)), partition_table(date(2018, 7, 1)))]
        assert client.state_writes[-1]["next_shard_date"] == "2018-07-02"

    def test_catch_up_advances_past_all_loaded_days(self):
        client = FakeClient(next_shard_date=date(2018, 7, 1))
        replay_loader.run_replay(client, catch_up=2)
        assert len(client.copied) == 3
        assert client.state_writes[-1]["next_shard_date"] == "2018-07-04"

    def test_complete_replay_copies_nothing_and_keeps_state(self):
        client = FakeClient(next_shard_date=date(2018, 10, 4))
        loaded = replay_loader.run_replay(client)
        assert loaded == []
        assert client.copied == []
        assert client.state_writes == []

    def test_never_issues_query_jobs(self):
        client = FakeClient(next_shard_date=date(2018, 7, 1))
        replay_loader.run_replay(client, catch_up=1)
        # FakeClient raises on any method beyond the free set (list_rows,
        # copy_table, load_table_from_json, get_table) — reaching here means
        # no client.query(...) call exists in the replay path.

    def test_reload_day_rejects_out_of_range(self):
        client = FakeClient(next_shard_date=date(2018, 7, 1))
        with pytest.raises(SystemExit):
            replay_loader.reload_day(client, date(2019, 1, 1))

    def test_reload_day_does_not_touch_state(self):
        client = FakeClient(next_shard_date=date(2018, 7, 1))
        replay_loader.reload_day(client, date(2018, 6, 15))
        assert client.copied == [
            (shard_table(date(2018, 6, 15)), partition_table(date(2018, 6, 15)))
        ]
        assert client.state_writes == []
