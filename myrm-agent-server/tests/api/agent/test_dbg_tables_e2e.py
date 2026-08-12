"""Temp debug: inspect DB tables present when running alongside workspace_rules."""
import os

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="requires key",
)
def test_dbg_tables(client: TestClient) -> None:
    from sqlalchemy import inspect

    from app.platform_utils import get_database_engine, get_session_factory
    import asyncio

    async def _list_tables():
        engine = get_database_engine()
        async with engine.connect() as conn:
            insp = await conn.run_sync(inspect)
            names = sorted(insp.get_table_names())
        return names

    tables = asyncio.run(_list_tables())
    print("\nDBG_TABLES user_configs=", "user_configs" in tables)
    print("DBG_TABLES count=", len(tables), "tables=", ",".join(tables[:40]), "...")
