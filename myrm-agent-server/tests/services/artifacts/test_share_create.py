"""Share creation service: one path for the share dialog and IM buttons, always registered."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.security.share.share_links import ShareKind, share_link_path
from app.database.models import Base
from app.database.models.artifact import Artifact
from app.services.artifacts.share.share_create import ShareRegistrationError, create_artifact_share
from app.services.artifacts.share.share_registry import is_token_revoked, list_active_shares
from app.services.artifacts.share.share_token import ArtifactShareClaims, parse_artifact_share_token
from app.services.audit.share_events import ShareSource

_MATERIALIZE = "app.services.artifacts.share.share_create.materialize_share_bundle"


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///file:testdb_share_create?mode=memory&cache=shared&uri=true")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def artifact_id(db_session: AsyncSession) -> str:
    artifact = Artifact(id=str(uuid.uuid4()), name="index.html", chat_id=str(uuid.uuid4()), is_deleted=False)
    db_session.add(artifact)
    await db_session.commit()
    return artifact.id


@pytest.mark.asyncio
async def test_created_share_is_snapshotted_registered_and_listed(db_session: AsyncSession, artifact_id: str) -> None:
    with patch(_MATERIALIZE, new_callable=AsyncMock) as materialize:
        created = await create_artifact_share(
            db_session, "/ws", artifact_id=artifact_id, version_id="ver-1", artifact_type="html", source=ShareSource.DIALOG
        )

    claims = parse_artifact_share_token(created.token)
    assert claims is not None
    assert (claims.artifact_id, claims.version_id, claims.exp) == (artifact_id, "ver-1", created.expires_at)
    materialize.assert_awaited_once_with(
        db_session,
        "/ws",
        ArtifactShareClaims(artifact_id=artifact_id, version_id="ver-1", exp=created.expires_at, artifact_type="html"),
    )
    assert await is_token_revoked(db_session, created.token) is False
    (row,) = await list_active_shares(db_session)
    assert (row.artifact_id, row.version_id, row.artifact_type) == (artifact_id, "ver-1", "html")
    assert row.password_protected is False
    assert row.share_path is None


@pytest.mark.asyncio
async def test_password_share_stores_the_path_its_token_cannot_rebuild(db_session: AsyncSession, artifact_id: str) -> None:
    with patch(_MATERIALIZE, new_callable=AsyncMock):
        created = await create_artifact_share(
            db_session,
            "/ws",
            artifact_id=artifact_id,
            version_id="ver-1",
            artifact_type="html",
            source=ShareSource.DIALOG,
            password="pw",
        )

    (row,) = await list_active_shares(db_session)
    assert row.password_protected is True
    assert row.share_path == share_link_path(ShareKind.ARTIFACT, created.token)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [FileNotFoundError("gone"), LookupError("no version"), ValueError("NO_VERSIONS")])
async def test_snapshot_failure_registers_nothing(db_session: AsyncSession, artifact_id: str, error: Exception) -> None:
    """A token that never got its snapshot must not exist as a listed, revocable link."""
    with patch(_MATERIALIZE, new_callable=AsyncMock, side_effect=error), pytest.raises(type(error)):
        await create_artifact_share(
            db_session, "/ws", artifact_id=artifact_id, version_id="ver-1", artifact_type="html", source=ShareSource.DIALOG
        )

    assert await list_active_shares(db_session) == []


@pytest.mark.asyncio
async def test_registration_failure_is_reported_as_a_share_error(db_session: AsyncSession, artifact_id: str) -> None:
    cause = RuntimeError("database is locked")
    with (
        patch(_MATERIALIZE, new_callable=AsyncMock),
        patch("app.services.artifacts.share.share_create.register_share", new_callable=AsyncMock, side_effect=cause),
        pytest.raises(ShareRegistrationError, match="Failed to register share link") as caught,
    ):
        await create_artifact_share(
            db_session, "/ws", artifact_id=artifact_id, version_id="ver-1", artifact_type=None, source=ShareSource.DIALOG
        )

    assert caught.value.__cause__ is cause
