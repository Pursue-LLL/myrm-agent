"""HTTP integration tests for POST /memory/import/readiness-recheck."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies import get_deploy_identity
from app.database.models import Base
from app.services.memory.imports.import_sessions import ImportReadinessRecheckFacts, MemoryImportSessionService
from tests.services.memory.test_import_sessions import _FakeMemoryManager
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="memory")


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def client(db_session: AsyncSession) -> TestClient:
    @asynccontextmanager
    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_deploy_identity] = lambda: {"id": "test_user", "username": "test"}
    with (
        patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
        patch("app.database.connection.get_session", _session_override),
        patch("app.services.memory.operations.crud.import_archive.get_session", _session_override),
    ):
        yield TestClient(app)
    app.dependency_overrides.pop(get_deploy_identity, None)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test_token"}


@pytest.mark.asyncio
async def test_readiness_recheck_http_returns_current_readiness(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    manager = _FakeMemoryManager()
    service = MemoryImportSessionService(db_session)
    payload = {"data": {"semantic": [{"content": "HTTP recheck.", "metadata": {}}]}}
    dry_run_id, _preview, _payload_hash, _expires_at = await service.create_dry_run(
        payload,
        "native_json",
        session_metadata={"source_has_api_keys": True},
    )
    confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)
    await service.save_post_import_diagnostic(
        import_batch_id=confirm.import_batch_id,
        diagnostic_run_id="diag-ready",
        diagnostic_status="ready",
        failed_count=0,
    )
    await service.save_post_import_readiness(
        import_batch_id=confirm.import_batch_id,
        readiness_status="critical",
        readiness_issues=[{"code": "providers_not_configured", "severity": "critical", "params": {}}],
        recheck_facts=ImportReadinessRecheckFacts(
            source_has_api_keys=True,
            diagnostic_status="ready",
            diagnostic_failed_count=0,
            mcp_config_count=0,
            workspace_rules_skipped=0,
        ),
    )

    with patch(
        "app.services.migration.source_secrets_importer.external_source_providers_configured",
        return_value=True,
    ):
        resp = client.post(
            "/api/v1/memory/import/readiness-recheck",
            json={"import_batch_id": confirm.import_batch_id},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["import_batch_id"] == confirm.import_batch_id
    assert body["readiness"]["status"] == "ready"
    assert body["readiness"]["issues"] == []


@pytest.mark.asyncio
async def test_readiness_recheck_http_404_for_unknown_batch(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    resp = client.post(
        "/api/v1/memory/import/readiness-recheck",
        json={"import_batch_id": "memory-import-batch:missing"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
