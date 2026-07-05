"""Unit tests for the incident injectors — pure logic and free-operation
boundaries; BigQuery is faked."""

from datetime import date

import pytest
from google.cloud import bigquery

from loader import incidents, replay_loader
from loader.replay_loader import FIRST_SHARD_DATE, ReplayState


class FakeStateClient:
    """Stub covering the state read/write surface used by skip-day."""

    def __init__(self, skip_runs: int = 0, days_loaded: int = 3):
        self._state = ReplayState(
            simulation_start_date=FIRST_SHARD_DATE,
            next_shard_date=date(2018, 6, 12 + days_loaded),
            skip_runs=skip_runs,
        )
        self.state_writes: list[dict] = []
        self.copied: list[tuple[str, str]] = []

    def list_rows(self, table, max_results=None):
        return [
            {
                "simulation_start_date": self._state.simulation_start_date,
                "next_shard_date": self._state.next_shard_date,
                "skip_runs": self._state.skip_runs,
            }
        ]

    def load_table_from_json(self, rows, table, job_config=None):
        self.state_writes.extend(rows)
        self._state = ReplayState(
            simulation_start_date=date.fromisoformat(rows[-1]["simulation_start_date"]),
            next_shard_date=date.fromisoformat(rows[-1]["next_shard_date"]),
            skip_runs=rows[-1]["skip_runs"],
        )

        class _Job:
            def result(self):
                return self

        return _Job()

    def copy_table(self, source, dest, job_config=None):
        self.copied.append((source, dest))

        class _Job:
            def result(self):
                return self

        return _Job()

    def get_table(self, table):
        class _T:
            num_rows = 50_000
            num_bytes = 35_000_000

        return _T()


class TestSkipDay:
    def test_increments_skip_runs(self):
        client = FakeStateClient()
        incidents.inject_skip_day(client)
        assert client.state_writes[-1]["skip_runs"] == 1

    def test_loader_consumes_skip_and_loads_nothing(self):
        client = FakeStateClient(skip_runs=1)
        loaded = replay_loader.run_replay(client)
        assert loaded == []
        assert client.copied == []
        assert client.state_writes[-1]["skip_runs"] == 0

    def test_loader_resumes_after_skips_consumed(self):
        client = FakeStateClient(skip_runs=1)
        replay_loader.run_replay(client)
        loaded = replay_loader.run_replay(client)
        assert len(loaded) == 1
        assert len(client.copied) == 1


class TestLastLoadedDay:
    def test_derives_day_before_next_shard(self):
        client = FakeStateClient(days_loaded=3)
        assert incidents.last_loaded_day(client) == date(2018, 6, 14)

    def test_rejects_empty_replay(self):
        client = FakeStateClient(days_loaded=0)
        with pytest.raises(SystemExit):
            incidents.last_loaded_day(client)


class TestRewriteSql:
    SCHEMA = [
        bigquery.SchemaField("event_date", "STRING"),
        bigquery.SchemaField("platform", "STRING"),
        bigquery.SchemaField("event_timestamp", "INTEGER"),
    ]

    def test_drop_column_nulls_with_cast(self):
        sql = incidents.build_rewrite_sql(self.SCHEMA, "platform", date(2018, 6, 14), 1.0)
        assert "cast(null as STRING) as platform" in sql
        assert "event_date" in sql
        assert "where _partitiondate = '2018-06-14'" in sql

    def test_null_spike_uses_rand(self):
        sql = incidents.build_rewrite_sql(self.SCHEMA, "platform", date(2018, 6, 14), 0.3)
        assert "if(rand() < 0.3, null, platform) as platform" in sql

    def test_partition_filter_always_present(self):
        sql = incidents.build_rewrite_sql(self.SCHEMA, "platform", date(2018, 6, 14), 0.5)
        assert "_partitiondate =" in sql

    def test_unknown_column_rejected(self):
        with pytest.raises(SystemExit):
            incidents.build_rewrite_sql(self.SCHEMA, "not_a_column", date(2018, 6, 14), 1.0)


class TestDuplicateDay:
    def test_appends_shard_to_partition(self):
        client = FakeStateClient()
        incidents.inject_duplicate_day(client, date(2018, 6, 14))
        assert client.copied == [
            (
                "firebase-public-project.analytics_153293282.events_20180614",
                "data-eng-491120.raw_floodit.events$20180614",
            )
        ]
