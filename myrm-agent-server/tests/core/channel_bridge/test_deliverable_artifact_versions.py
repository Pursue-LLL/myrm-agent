"""Unit tests for the batch lookup of the latest artifact version ids behind the share links."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestFetchArtifactVersions:
    """Tests for fetch_artifact_versions DB batch lookup."""

    @pytest.mark.asyncio
    async def test_empty_ids_returns_empty(self):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            fetch_artifact_versions,
        )

        result = await fetch_artifact_versions([])
        assert result == {}

    @pytest.mark.asyncio
    @patch(
        "app.database.connection.get_session",
        side_effect=RuntimeError("DB unavailable"),
    )
    async def test_db_exception_returns_empty(self, mock_session: MagicMock):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            fetch_artifact_versions,
        )

        result = await fetch_artifact_versions(["art-001"])
        assert result == {}

    @pytest.mark.asyncio
    async def test_real_db_latest_version_selected(self) -> None:
        """Real SQLite lookup picks the newest version per artifact."""
        from contextlib import asynccontextmanager
        from unittest.mock import patch

        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker

        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            fetch_artifact_versions,
        )
        from app.database.models import Base
        from app.database.models.artifact import Artifact, ArtifactVersion

        engine = create_async_engine("sqlite+aiosqlite:///file:deep_links_test?mode=memory&cache=shared&uri=true")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as db:
            db.add_all(
                [
                    Artifact(
                        id="art-1",
                        name="report",
                        versions=[
                            ArtifactVersion(
                                id="v-old",
                                vault_uri="vault://old",
                                sha256_hash="a" * 64,
                            ),
                            ArtifactVersion(
                                id="v-new",
                                vault_uri="vault://new",
                                sha256_hash="b" * 64,
                            ),
                        ],
                    ),
                    Artifact(
                        id="art-2",
                        name="notes",
                        versions=[
                            ArtifactVersion(
                                id="v-solo",
                                vault_uri="vault://solo",
                                sha256_hash="c" * 64,
                            ),
                        ],
                    ),
                    Artifact(
                        id="art-3",
                        name="no versions",
                        versions=[],
                    ),
                    Artifact(
                        id="art-4",
                        name="deleted",
                        is_deleted=True,
                        versions=[
                            ArtifactVersion(
                                id="v-del",
                                vault_uri="vault://del",
                                sha256_hash="d" * 64,
                            ),
                        ],
                    ),
                ]
            )
            await db.commit()

            # Give the two versions distinct creation times so the max pick is deterministic.
            stmt = select(ArtifactVersion).where(ArtifactVersion.artifact_id == "art-1")
            rows = (await db.execute(stmt)).scalars().all()
            import datetime

            rows[0].created_at = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
            rows[1].created_at = datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc)
            await db.commit()

            @asynccontextmanager
            async def fake_get_session():
                yield db

            with patch("app.database.connection.get_session", new=fake_get_session):
                result = await fetch_artifact_versions(["art-1", "art-2", "art-3", "art-4"])

        assert result == {"art-1": "v-new", "art-2": "v-solo"}
        await engine.dispose()
