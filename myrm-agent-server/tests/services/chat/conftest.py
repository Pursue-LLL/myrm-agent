import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.repositories.conversation_recall_repo import CONVERSATION_RECALL_SCHEMA_SQL


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///file:testdb_chat?mode=memory&cache=shared&uri=true")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        from app.database.migrations import ensure_raw_sql_schema

        await ensure_raw_sql_schema(engine)

    TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Bind UnitOfWork to this in-memory database for repository calls.
    import app.database.repositories.uow as uow_module

    original_factory = getattr(uow_module, "get_session_factory", None)
    uow_module.get_session_factory = lambda: TestingSessionLocal

    async with TestingSessionLocal() as session:
        yield session

    if original_factory:
        uow_module.get_session_factory = original_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def fts_db():
    engine = create_async_engine("sqlite+aiosqlite:///file:testdb_search?mode=memory&cache=shared&uri=true")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                content=messages,
                content_rowid=rowid,
                tokenize='trigram'
            )
        """)
        )
        await conn.execute(
            text("""
            CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
            END
        """)
        )
        await conn.execute(
            text("""
            CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.rowid, old.content);
            END
        """)
        )
        await conn.execute(
            text("""
            CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.rowid, old.content);
                INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
            END
        """)
        )
        for sql in CONVERSATION_RECALL_SCHEMA_SQL:
            await conn.execute(text(sql))

    test_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import app.database.repositories.uow as uow_module

    original_factory = getattr(uow_module, "get_session_factory", None)
    uow_module.get_session_factory = lambda: test_session

    async with test_session() as session:
        yield session

    if original_factory:
        uow_module.get_session_factory = original_factory

    await engine.dispose()
