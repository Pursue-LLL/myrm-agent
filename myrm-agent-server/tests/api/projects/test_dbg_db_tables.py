"""Temp debug: print DB tables visible from the projects dir under shared session."""

import pytest


@pytest.mark.e2e
def test_dbg_db_tables() -> None:
    from app.platform_utils import get_database_engine

    def _list_sync(conn) -> list[str]:
        from sqlalchemy import inspect

        return sorted(inspect(conn).get_table_names())

    async def _run() -> None:
        engine = get_database_engine()
        async with engine.connect() as conn:
            tables = await conn.run_sync(_list_sync)
            print(
                "\nDBG_DB user_configs=",
                "user_configs" in tables,
                "n=",
                len(tables),
                flush=True,
            )
            print("DBG_DB tables=", ",".join(tables[:80]), flush=True)

    import asyncio

    asyncio.run(_run())
