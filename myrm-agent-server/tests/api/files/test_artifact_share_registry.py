"""Tests for artifact share-link lifecycle (registry + management API)."""

from __future__ import annotations

import logging
import time
import uuid
from calendar import timegm
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_workspace_root
from app.api.files.artifact_share_api import public_router
from app.api.files.artifact_share_api import router as share_router
from app.core.infra.limiter import limiter
from app.database.connection import get_db
from app.database.models import Base
from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.artifacts.share_bundle import bundle_dir_for_claims
from app.services.artifacts.share_registry import (
    is_token_revoked,
    list_active_shares,
    purge_expired_shares,
    register_share,
    revoke_share,
    token_fingerprint,
)
from app.services.artifacts.share_token import (
    create_artifact_share_token,
    parse_artifact_share_token,
    rebuild_artifact_share_token,
)
from app.services.hosting.packager import PublishFile


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:testdb_share_registry?mode=memory&cache=shared&uri=true"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def share_client(db_session, tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        "app.services.artifacts.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    limiter.enabled = False
    test_app = FastAPI()
    test_app.include_router(share_router)
    test_app.include_router(public_router, prefix="/public/artifact-share")

    async def override_get_db():
        yield db_session

    async def override_workspace_root() -> str:
        return str(tmp_path)

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_workspace_root] = override_workspace_root
    with TestClient(test_app) as test_client:
        yield test_client
    limiter.enabled = True


@pytest.fixture
async def html_artifact(db_session):
    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="index.html",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri="vault://html",
        sha256_hash="hash",
    )
    db_session.add(version)
    await db_session.commit()
    await db_session.refresh(artifact)
    return artifact


def _single_file_files():
    return {
        "index.html": PublishFile(
            path="index.html", content="<html></html>", encoding="utf-8"
        ),
    }


def _expires_in_days(days: int) -> int:
    return int(time.time()) + days * 24 * 3600


# ---------------------------------------------------------------------------
# register_share service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_share_persists_fingerprint(db_session) -> None:
    token, exp = create_artifact_share_token("art-1", "ver-1", ttl_seconds=3600)
    record = await register_share(
        db_session,
        token=token,
        artifact_id="art-1",
        version_id="ver-1",
        artifact_type="html",
        password_protected=True,
        expires_at_unix=exp,
    )
    assert record.token_fingerprint == token_fingerprint(token)
    assert record.password_protected is True
    assert record.revoked_at is None
    assert timegm(record.expires_at.timetuple()) == pytest.approx(exp)


@pytest.mark.asyncio
async def test_rebuild_unprotected_token_matches_original(db_session) -> None:
    """An unprotected token is deterministically rebuilt from registry fields."""
    token, exp = create_artifact_share_token(
        "art-1", "ver-1", ttl_seconds=3600, artifact_type="html"
    )
    record = await register_share(
        db_session,
        token=token,
        artifact_id="art-1",
        version_id="ver-1",
        artifact_type="html",
        password_protected=False,
        expires_at_unix=exp,
    )
    rebuilt = rebuild_artifact_share_token(
        record.artifact_id,
        record.version_id,
        expires_at_unix=timegm(record.expires_at.timetuple()),
        artifact_type=record.artifact_type,
    )
    assert rebuilt == token


@pytest.mark.asyncio
async def test_register_share_idempotent_on_same_token(db_session) -> None:
    token, exp = create_artifact_share_token("art-1", "ver-1", ttl_seconds=3600)
    first = await register_share(
        db_session,
        token=token,
        artifact_id="art-1",
        version_id="ver-1",
        artifact_type=None,
        password_protected=False,
        expires_at_unix=exp,
    )
    second = await register_share(
        db_session,
        token=token,
        artifact_id="art-1",
        version_id="ver-1",
        artifact_type=None,
        password_protected=False,
        expires_at_unix=exp,
    )
    assert first.id == second.id


@pytest.mark.asyncio
async def test_register_share_reraises_when_conflict_has_no_existing() -> None:
    """A unique-constraint conflict with no resolvable existing row must
    surface as IntegrityError instead of being silently swallowed."""
    token, exp = create_artifact_share_token("art-1", "ver-1", ttl_seconds=3600)

    fake_session = AsyncMock(spec=AsyncSession)

    class _EmptyScalars:
        def first(self) -> None:
            return None

    class _EmptyResult:
        def scalars(self) -> _EmptyScalars:
            return _EmptyScalars()

    fake_session.execute.return_value = _EmptyResult()
    fake_session.commit.side_effect = IntegrityError(
        "INSERT INTO artifact_share_records ...", {}, RuntimeError("unique violation")
    )

    with pytest.raises(IntegrityError):
        await register_share(
            fake_session,
            token=token,
            artifact_id="art-1",
            version_id="ver-1",
            artifact_type=None,
            password_protected=False,
            expires_at_unix=exp,
        )
    fake_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# is_token_revoked service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_token_revoked_unknown_token_returns_false(db_session) -> None:
    token, _ = create_artifact_share_token("art-1", "ver-1", ttl_seconds=3600)
    assert await is_token_revoked(db_session, token) is False


@pytest.mark.asyncio
async def test_is_token_revoked_after_revoke(db_session) -> None:
    token, exp = create_artifact_share_token("art-1", "ver-1", ttl_seconds=3600)
    record = await register_share(
        db_session,
        token=token,
        artifact_id="art-1",
        version_id="ver-1",
        artifact_type=None,
        password_protected=False,
        expires_at_unix=exp,
    )
    assert await is_token_revoked(db_session, token) is False
    assert await revoke_share(db_session, record.id) is True
    assert await is_token_revoked(db_session, token) is True


# ---------------------------------------------------------------------------
# list_active_shares / revoke_share service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_active_shares_excludes_revoked_and_expired(
    db_session, html_artifact
) -> None:
    token_a, exp_a = create_artifact_share_token(
        html_artifact.id, "ver-a", ttl_seconds=3600
    )
    await register_share(
        db_session,
        token=token_a,
        artifact_id=html_artifact.id,
        version_id="ver-a",
        artifact_type="html",
        password_protected=False,
        expires_at_unix=exp_a,
    )
    token_b, exp_b = create_artifact_share_token(
        html_artifact.id, "ver-b", ttl_seconds=3600
    )
    record_b = await register_share(
        db_session,
        token=token_b,
        artifact_id=html_artifact.id,
        version_id="ver-b",
        artifact_type="html",
        password_protected=False,
        expires_at_unix=exp_b,
    )
    await revoke_share(db_session, record_b.id)

    rows = await list_active_shares(db_session)
    assert len(rows) == 1
    assert rows[0].artifact_name == "index.html"
    assert rows[0].artifact_type == "html"


@pytest.mark.asyncio
async def test_revoke_share_unknown_id_returns_false(db_session) -> None:
    assert await revoke_share(db_session, "does-not-exist") is False


@pytest.mark.asyncio
async def test_revoke_share_deletes_bundle(db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.artifacts.share_bundle.settings.database.state_dir",
        str(tmp_path),
    )
    token, exp = create_artifact_share_token("art-1", "ver-1", ttl_seconds=3600)
    record = await register_share(
        db_session,
        token=token,
        artifact_id="art-1",
        version_id="ver-1",
        artifact_type=None,
        password_protected=False,
        expires_at_unix=exp,
    )
    claims = parse_artifact_share_token(token)
    assert claims is not None
    bundle_dir = bundle_dir_for_claims(claims)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "index.html").write_text("<html/>")

    assert await revoke_share(db_session, record.id) is True
    assert not bundle_dir.exists()


@pytest.mark.asyncio
async def test_revoke_share_writes_audit_log(db_session, caplog) -> None:
    """O7: successful revocations emit an INFO audit log for compliance tracing."""
    token, exp = create_artifact_share_token("art-1", "ver-1", ttl_seconds=3600)
    record = await register_share(
        db_session,
        token=token,
        artifact_id="art-1",
        version_id="ver-1",
        artifact_type=None,
        password_protected=False,
        expires_at_unix=exp,
    )

    with caplog.at_level(logging.INFO, logger="app.services.artifacts.share_registry"):
        assert await revoke_share(db_session, record.id) is True

    assert any(
        "Revoked artifact share link" in message and "record=" in message
        for message in caplog.messages
    )


@pytest.mark.asyncio
async def test_purge_expired_shares_removes_stale_records(db_session) -> None:
    token, exp = create_artifact_share_token("art-1", "ver-1", ttl_seconds=3600)
    record = await register_share(
        db_session,
        token=token,
        artifact_id="art-1",
        version_id="ver-1",
        artifact_type=None,
        password_protected=False,
        expires_at_unix=exp,
    )
    # Backdate the expiry beyond the retention window.
    record.expires_at = datetime.now(UTC) - timedelta(days=61)
    await db_session.commit()

    assert await purge_expired_shares(db_session) == 1
    assert await list_active_shares(db_session) == []


# ---------------------------------------------------------------------------
# API: create registers, list, revoke, public access after revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_registers_record(share_client, html_artifact) -> None:
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    token = response.json()["token"]
    assert token_fingerprint(token) is not None


@pytest.mark.asyncio
async def test_list_shares_endpoint(share_client, html_artifact) -> None:
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert create_resp.status_code == 200
    original_token = create_resp.json()["token"]

    list_resp = share_client.get("/shares")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert len(payload) == 1
    row = payload[0]
    assert row["artifact_name"] == "index.html"
    assert row["artifact_type"] == "html"
    assert row["password_protected"] is False
    assert row["expires_at"] > int(time.time())
    # Unprotected shares expose a rebuilt share_path that points at the token.
    assert row["share_path"] == f"/api/v1/public/artifact-share/{original_token}"
    # No public ingress configured in tests, so no absolute share_url.
    assert row["share_url"] is None


@pytest.mark.asyncio
async def test_list_shares_endpoint_exposes_absolute_share_url(
    share_client, html_artifact
) -> None:
    """List exposes an absolute share_url once public ingress is configured."""
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert create_resp.status_code == 200
    token = create_resp.json()["token"]

    with patch(
        "app.api.files.artifact_share_api.get_public_ingress_base_url",
        new_callable=AsyncMock,
        return_value="https://myrm-x.example.com",
    ):
        list_resp = share_client.get("/shares")
    assert list_resp.status_code == 200
    row = list_resp.json()[0]
    assert row["share_url"] == (
        f"https://myrm-x.example.com/api/v1/public/artifact-share/{token}"
    )


@pytest.mark.asyncio
async def test_list_shares_password_protected_has_no_share_path(
    share_client, html_artifact
) -> None:
    """Password-protected shares cannot rebuild the token (password not stored)."""
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    assert create_resp.status_code == 200

    list_resp = share_client.get("/shares")
    assert list_resp.status_code == 200
    row = list_resp.json()[0]
    assert row["password_protected"] is True
    assert row["share_path"] is None


@pytest.mark.asyncio
async def test_revoke_share_endpoint_and_public_denied(
    share_client, html_artifact, tmp_path
) -> None:
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert create_resp.status_code == 200

    list_resp = share_client.get("/shares")
    record_id = list_resp.json()[0]["id"]

    delete_resp = share_client.delete(f"/shares/{record_id}")
    assert delete_resp.status_code == 204

    # Repeating the delete is idempotent (204).
    repeat_resp = share_client.delete(f"/shares/{record_id}")
    assert repeat_resp.status_code == 204

    list_after = share_client.get("/shares")
    assert list_after.json() == []


@pytest.mark.asyncio
async def test_revoke_unknown_record_returns_404(share_client) -> None:
    response = share_client.delete(f"/shares/{uuid.uuid4()}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_share_failure_returns_500(share_client, html_artifact) -> None:
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ), patch(
        "app.api.files.artifact_share_api.register_share",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db down"),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 500
    assert "register" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_public_access_denied_after_revoke(
    share_client, html_artifact, tmp_path
) -> None:
    """A revoked token returns 404 even though its bundle was materialized."""
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert create_resp.status_code == 200
    token = create_resp.json()["token"]

    # Ensure the public URL is servable before revoke.
    serve_before = share_client.get(
        f"/public/artifact-share/{token}", follow_redirects=False
    )
    assert serve_before.status_code == 200

    record_id = share_client.get("/shares").json()[0]["id"]
    assert share_client.delete(f"/shares/{record_id}").status_code == 204

    # Registry gate rejects regardless of on-disk bundle state.
    serve_after = share_client.get(
        f"/public/artifact-share/{token}", follow_redirects=False
    )
    assert serve_after.status_code == 404
    assert "revoked" in serve_after.json()["detail"]


@pytest.mark.asyncio
async def test_revoked_password_share_skips_password_gate(
    share_client, html_artifact
) -> None:
    """A revoked password-protected token 404s immediately, without a gate page."""
    with patch(
        "app.services.artifacts.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _single_file_files()),
    ):
        create_resp = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", "password": "s3cret"},
        )
    assert create_resp.status_code == 200
    token = create_resp.json()["token"]

    record_id = share_client.get("/shares").json()[0]["id"]
    assert share_client.delete(f"/shares/{record_id}").status_code == 204

    denied = share_client.get(
        f"/public/artifact-share/{token}", follow_redirects=False
    )
    assert denied.status_code == 404
    assert "revoked" in denied.json()["detail"]
