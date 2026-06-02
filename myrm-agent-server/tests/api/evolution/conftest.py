"""Evolution API test fixtures."""

import pytest
import pytest_asyncio


@pytest.fixture(autouse=True)
def mock_myrm_data_dir(tmp_path, monkeypatch):
    """Isolate each test to a fresh workspace + SQLite file."""
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path))


@pytest_asyncio.fixture(autouse=True)
async def init_evolution_test_db():
    import app.database.models  # noqa: F401 — register all tables on Base.metadata
    from app.database.models import Base
    from app.platform_utils import get_database_engine, reset_database_engine

    await reset_database_engine()
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    await reset_database_engine()
