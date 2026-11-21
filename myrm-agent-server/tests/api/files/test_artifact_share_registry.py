"""Tests for the artifact share-link registry service: register, gate check, list, revoke, purge."""

from __future__ import annotations

import logging
from calendar import timegm
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.artifacts.share.share_bundle import bundle_dir_for_claims
from app.services.artifacts.share.share_registry import (
    is_token_revoked,
    list_active_shares,
    purge_expired_shares,
    register_share,
    revoke_share,
    token_fingerprint,
)
from app.services.artifacts.share.share_token import (
    create_artifact_share_token,
    parse_artifact_share_token,
    rebuild_artifact_share_token,
)

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
async def test_register_share_persists_password_share_path(db_session, html_artifact) -> None:
    """Password-protected rows keep their share_path so the GUI can offer
    copy/open links even though the token itself cannot be rebuilt."""
    token, exp = create_artifact_share_token(html_artifact.id, "ver-1", ttl_seconds=3600)
    record = await register_share(
        db_session,
        token=token,
        artifact_id=html_artifact.id,
        version_id="ver-1",
        artifact_type="html",
        password_protected=True,
        expires_at_unix=exp,
        share_path=f"/api/v1/public/artifact-share/{token}",
    )
    assert record.share_path == f"/api/v1/public/artifact-share/{token}"
    rows = await list_active_shares(db_session)
    assert rows[0].share_path == f"/api/v1/public/artifact-share/{token}"


@pytest.mark.asyncio
async def test_register_share_keeps_unprotected_share_path_null(db_session, html_artifact) -> None:
    """Unprotected rows stay stateless; the path is rebuilt on demand."""
    token, exp = create_artifact_share_token(html_artifact.id, "ver-1", ttl_seconds=3600)
    record = await register_share(
        db_session,
        token=token,
        artifact_id=html_artifact.id,
        version_id="ver-1",
        artifact_type="html",
        password_protected=False,
        expires_at_unix=exp,
    )
    assert record.share_path is None
    rows = await list_active_shares(db_session)
    assert rows[0].share_path is None


@pytest.mark.asyncio
async def test_rebuild_unprotected_token_matches_original(db_session) -> None:
    """An unprotected token is deterministically rebuilt from registry fields."""
    token, exp = create_artifact_share_token("art-1", "ver-1", ttl_seconds=3600, artifact_type="html")
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
async def test_list_active_shares_excludes_revoked_and_expired(db_session, html_artifact) -> None:
    token_a, exp_a = create_artifact_share_token(html_artifact.id, "ver-a", ttl_seconds=3600)
    await register_share(
        db_session,
        token=token_a,
        artifact_id=html_artifact.id,
        version_id="ver-a",
        artifact_type="html",
        password_protected=False,
        expires_at_unix=exp_a,
    )
    token_b, exp_b = create_artifact_share_token(html_artifact.id, "ver-b", ttl_seconds=3600)
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
        "app.services.artifacts.share.share_bundle.settings.database.state_dir",
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
    """Successful revocations emit an INFO audit log for compliance tracing."""
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

    with caplog.at_level(logging.INFO, logger="app.services.artifacts.share.share_registry"):
        assert await revoke_share(db_session, record.id) is True

    assert any("Revoked artifact share link" in message and "record=" in message for message in caplog.messages)


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
