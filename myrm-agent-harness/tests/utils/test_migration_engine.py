import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from myrm_agent_harness.utils.db.migration_engine import MigrationStatement, StatefulMigrationEngine


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_migration_engine_fresh_install(engine):
    engine_runner = StatefulMigrationEngine(engine)

    migrations = [
        MigrationStatement(version=0, sql="CREATE TABLE test1 (id INTEGER PRIMARY KEY)"),
        MigrationStatement(version=1, sql="CREATE TABLE test2 (id INTEGER PRIMARY KEY)"),
    ]

    report = await engine_runner.run_migrations(migrations)

    assert report.applied_count == 2
    assert report.skipped_count == 0
    assert report.failed_count == 0
    assert not report.baselined

    # Verify tables exist
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = {row[0] for row in res}
        assert "test1" in tables
        assert "test2" in tables
        assert "_schema_migrations" in tables


@pytest.mark.asyncio
async def test_migration_engine_baseline(engine):
    # Simulate an existing database without the state table
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))

    engine_runner = StatefulMigrationEngine(
        engine, baseline_check_sql="SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
    )

    migrations = [
        MigrationStatement(version=0, sql="CREATE TABLE users (id INTEGER PRIMARY KEY)"),  # This would fail if executed
        MigrationStatement(version=1, sql="ALTER TABLE users ADD COLUMN name TEXT"),
    ]

    report = await engine_runner.run_migrations(migrations)

    assert report.applied_count == 0
    assert report.skipped_count == 2
    assert report.failed_count == 0
    assert report.baselined

    # Verify state table was created and populated
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT version, checksum FROM _schema_migrations"))
        rows = list(res)
        assert len(rows) == 2
        assert rows[0][0] == 0
        assert rows[0][1].startswith("baselined:")
        assert rows[1][0] == 1
        assert rows[1][1].startswith("baselined:")

        # Assert PRAGMA user_version synchronized to max version
        uv_res = await conn.execute(text("PRAGMA user_version"))
        assert uv_res.scalar() == 1


@pytest.mark.asyncio
async def test_migration_engine_failure(engine):
    engine_runner = StatefulMigrationEngine(engine)

    migrations = [
        MigrationStatement(version=0, sql="CREATE TABLE test1 (id INTEGER PRIMARY KEY)"),
        MigrationStatement(version=1, sql="INVALID SQL SYNTAX"),
        MigrationStatement(version=2, sql="CREATE TABLE test2 (id INTEGER PRIMARY KEY)"),
    ]

    report = await engine_runner.run_migrations(migrations)

    assert report.applied_count == 1
    assert report.failed_count == 1
    assert report.failed_version == 1
    assert "syntax error" in report.error_message.lower()

    # Verify state table only has version 0
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT version FROM _schema_migrations"))
        rows = list(res)
        assert len(rows) == 1
        assert rows[0][0] == 0


@pytest.mark.asyncio
async def test_migration_engine_checksum_tampering(engine):
    engine_runner = StatefulMigrationEngine(engine)

    migrations_v1 = [
        MigrationStatement(version=0, sql="CREATE TABLE test1 (id INTEGER PRIMARY KEY)"),
    ]

    # First run: apply migration V0
    report = await engine_runner.run_migrations(migrations_v1)
    assert report.applied_count == 1

    # Second run: modify the SQL of V0 (tampering)
    migrations_v2 = [
        MigrationStatement(version=0, sql="CREATE TABLE test1 (id INTEGER PRIMARY KEY, name TEXT)"),
    ]

    report = await engine_runner.run_migrations(migrations_v2)
    assert report.skipped_count == 1, "Tampered migration should be skipped (warning-only)"


@pytest.mark.asyncio
async def test_migration_engine_idempotent_skip_duplicate_column(engine):
    """ALTER TABLE ADD COLUMN whose target column already exists must not abort boot.

    Reproduces the production failure where parallel sandbox sessions mutate the
    schema out-of-band, leaving `_schema_migrations` short of a bookkeeping row.
    The engine must record the migration as idempotently skipped instead of
    raising RuntimeError.
    """
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE agents (id INTEGER PRIMARY KEY, name TEXT)"))

    engine_runner = StatefulMigrationEngine(engine)

    migrations = [
        MigrationStatement(version=0, sql="CREATE TABLE IF NOT EXISTS agents (id INTEGER PRIMARY KEY)"),
        MigrationStatement(version=1, sql="ALTER TABLE agents ADD COLUMN name TEXT"),
        MigrationStatement(version=2, sql="ALTER TABLE agents ADD COLUMN created_at TIMESTAMP"),
    ]

    report = await engine_runner.run_migrations(migrations)

    assert report.failed_count == 0, f"Idempotent error must not fail: {report.error_message}"
    assert report.applied_count == 2, "V0 (IF NOT EXISTS) and V2 (new column) succeed"
    assert report.skipped_count == 1, "V1 (ALTER duplicate column) idempotently skipped"

    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT version, checksum FROM _schema_migrations ORDER BY version"))
        rows = list(res)
        assert {r[0] for r in rows} == {0, 1, 2}
        idempotent_marks = [r[1] for r in rows if r[1].startswith("idempotent:")]
        assert len(idempotent_marks) == 1, "Only V1 should be flagged idempotent"


@pytest.mark.asyncio
async def test_migration_engine_idempotent_skip_index_already_exists(engine):
    """CREATE INDEX whose target already exists must skip without aborting."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE chats (id INTEGER PRIMARY KEY, status TEXT)"))
        await conn.execute(text("CREATE INDEX idx_chats_status ON chats(status)"))

    engine_runner = StatefulMigrationEngine(engine)

    migrations = [
        MigrationStatement(version=0, sql="CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY)"),
        MigrationStatement(version=1, sql="CREATE INDEX idx_chats_status ON chats(status)"),
    ]

    report = await engine_runner.run_migrations(migrations)

    assert report.failed_count == 0
    assert report.applied_count == 1, "V0 (IF NOT EXISTS) succeeds without error"
    assert report.skipped_count == 1, "V1 (CREATE INDEX duplicate) idempotently skipped"


@pytest.mark.asyncio
async def test_migration_engine_idempotent_skip_drop_nonexistent_column(engine):
    """DROP COLUMN targeting a nonexistent column must skip without aborting.

    Reproduces the production failure where artifacts table never had
    deployment_url but a migration tries to drop it.
    """
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE artifacts (id INTEGER PRIMARY KEY, name TEXT)"))

    engine_runner = StatefulMigrationEngine(engine)

    migrations = [
        MigrationStatement(version=0, sql="CREATE TABLE IF NOT EXISTS artifacts (id INTEGER PRIMARY KEY)"),
        MigrationStatement(version=1, sql="ALTER TABLE artifacts DROP COLUMN nonexistent_col"),
        MigrationStatement(version=2, sql="ALTER TABLE artifacts ADD COLUMN description TEXT"),
    ]

    report = await engine_runner.run_migrations(migrations)

    assert report.failed_count == 0, f"DROP nonexistent column must not fail: {report.error_message}"
    assert report.applied_count == 2, "V0 and V2 succeed"
    assert report.skipped_count == 1, "V1 (DROP nonexistent column) idempotently skipped"

    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT version, checksum FROM _schema_migrations ORDER BY version"))
        rows = list(res)
        assert {r[0] for r in rows} == {0, 1, 2}
        idempotent_marks = [r[1] for r in rows if r[1].startswith("idempotent:")]
        assert len(idempotent_marks) == 1, "Only V1 should be flagged idempotent"


def test_drift_shaped_skip_distinguishes_a_real_gap_from_a_drop() -> None:
    """A missing column on UPDATE/ALTER is drift; on DROP COLUMN it is expected."""
    from myrm_agent_harness.utils.db.migration_engine import _is_drift_shaped_skip

    assert _is_drift_shaped_skip("no such column: foo", "UPDATE t SET foo = 1")
    assert _is_drift_shaped_skip("no such column: foo", "ALTER TABLE t ADD COLUMN bar TEXT")
    assert not _is_drift_shaped_skip(
        "no such column: deployment_url", "ALTER TABLE artifacts DROP COLUMN deployment_url"
    )
    assert not _is_drift_shaped_skip("duplicate column name: foo", "ALTER TABLE t ADD COLUMN foo TEXT")


async def _table_names(engine) -> set[str]:
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        return {row[0] for row in res}


@pytest.mark.asyncio
async def test_has_pending_is_true_without_a_state_table_and_does_not_create_one(engine):
    migrations = [MigrationStatement(version=0, sql="CREATE TABLE test1 (id INTEGER PRIMARY KEY)")]

    assert await StatefulMigrationEngine(engine).has_pending(migrations) is True

    assert "_schema_migrations" not in await _table_names(engine)


@pytest.mark.asyncio
async def test_has_pending_is_false_once_every_statement_is_recorded(engine):
    engine_runner = StatefulMigrationEngine(engine)
    migrations = [
        MigrationStatement(version=0, sql="CREATE TABLE test1 (id INTEGER PRIMARY KEY)"),
        MigrationStatement(version=1, sql="CREATE TABLE test2 (id INTEGER PRIMARY KEY)"),
    ]
    await engine_runner.run_migrations(migrations)

    assert await engine_runner.has_pending(migrations) is False


@pytest.mark.asyncio
async def test_has_pending_sees_a_statement_appended_after_the_last_run(engine):
    engine_runner = StatefulMigrationEngine(engine)
    first = MigrationStatement(version=0, sql="CREATE TABLE test1 (id INTEGER PRIMARY KEY)")
    await engine_runner.run_migrations([first])
    appended = MigrationStatement(version=1, sql="ALTER TABLE test1 ADD COLUMN note TEXT")

    assert await engine_runner.has_pending([first, appended]) is True


@pytest.mark.asyncio
async def test_has_pending_treats_a_baselined_database_as_up_to_date(engine):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
    engine_runner = StatefulMigrationEngine(
        engine, baseline_check_sql="SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
    )
    migrations = [MigrationStatement(version=0, sql="CREATE TABLE users (id INTEGER PRIMARY KEY)")]
    await engine_runner.run_migrations(migrations)

    assert await engine_runner.has_pending(migrations) is False


USERS_EXISTS = "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"


class _KilledError(Exception):
    """Stands in for the process dying while the baseline rows are being written."""


async def _recorded_versions(engine) -> list[int]:
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT version FROM _schema_migrations ORDER BY version"))
        return [row[0] for row in res]


async def _user_version(engine) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("PRAGMA user_version"))).scalar()


@pytest.mark.asyncio
async def test_a_start_killed_before_its_baseline_committed_baselines_on_the_next_start(engine, monkeypatch):
    """The state table is committed before the baseline rows, so a kill between them leaves it empty.

    Replaying the statements then fails on every later start; the next start has to finish the baseline.
    """
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
    runner = StatefulMigrationEngine(engine, baseline_check_sql=USERS_EXISTS)
    migrations = [
        # Replaying this fails against the existing schema: the table it alters was retired long ago.
        MigrationStatement(version=0, sql="ALTER TABLE retired ADD COLUMN note TEXT"),
        MigrationStatement(version=1, sql="ALTER TABLE users ADD COLUMN name TEXT"),
    ]
    real_checksum = StatefulMigrationEngine._compute_checksum
    seen: list[str] = []

    def die_on_the_second_row(self, sql):
        seen.append(sql)
        if len(seen) == 2:
            raise _KilledError
        return real_checksum(self, sql)

    monkeypatch.setattr(StatefulMigrationEngine, "_compute_checksum", die_on_the_second_row)
    with pytest.raises(_KilledError):
        await runner.run_migrations(migrations)
    monkeypatch.undo()

    assert "_schema_migrations" in await _table_names(engine)
    assert await _recorded_versions(engine) == [], "the baseline is all-or-nothing"

    report = await runner.run_migrations(migrations)

    assert (report.baselined, report.failed_count, report.applied_count) == (True, 0, 0)
    assert await _recorded_versions(engine) == [0, 1]
    assert await _user_version(engine) == 1


@pytest.mark.asyncio
async def test_an_empty_state_table_over_an_empty_schema_still_applies_every_statement(engine):
    await StatefulMigrationEngine(engine).run_migrations([])  # leaves an empty state table behind
    runner = StatefulMigrationEngine(engine, baseline_check_sql=USERS_EXISTS)

    report = await runner.run_migrations(
        [MigrationStatement(version=0, sql="CREATE TABLE users (id INTEGER PRIMARY KEY)")]
    )

    assert (report.baselined, report.applied_count, report.failed_count) == (False, 1, 0)


@pytest.mark.asyncio
async def test_a_partly_recorded_state_table_resumes_instead_of_baselining(engine):
    first = MigrationStatement(version=0, sql="CREATE TABLE users (id INTEGER PRIMARY KEY)")
    await StatefulMigrationEngine(engine).run_migrations([first])
    runner = StatefulMigrationEngine(engine, baseline_check_sql=USERS_EXISTS)
    later = MigrationStatement(version=1, sql="ALTER TABLE users ADD COLUMN name TEXT")

    report = await runner.run_migrations([first, later])

    assert (report.baselined, report.applied_count, report.failed_count) == (False, 1, 0)
    async with engine.connect() as conn:
        assert "name" in {row[1] for row in await conn.execute(text("PRAGMA table_info(users)"))}


@pytest.mark.asyncio
async def test_two_starts_that_both_decide_to_baseline_do_not_collide(tmp_path):
    race_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'race.db'}")
    try:
        async with race_engine.begin() as conn:
            await conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        both_decided = asyncio.Barrier(2)

        class Racing(StatefulMigrationEngine):
            async def _needs_baseline(self) -> bool:
                decided = await super()._needs_baseline()
                await both_decided.wait()  # neither writes before both have seen an empty state table
                return decided

        migrations = [
            MigrationStatement(version=v, sql=f"CREATE TABLE t{v} (id INTEGER PRIMARY KEY)") for v in range(3)
        ]
        async with asyncio.timeout(30):
            reports = await asyncio.gather(
                *(Racing(race_engine, baseline_check_sql=USERS_EXISTS).run_migrations(migrations) for _ in range(2))
            )

        assert [(r.baselined, r.failed_count) for r in reports] == [(True, 0), (True, 0)]
        assert await _recorded_versions(race_engine) == [0, 1, 2]
    finally:
        await race_engine.dispose()
