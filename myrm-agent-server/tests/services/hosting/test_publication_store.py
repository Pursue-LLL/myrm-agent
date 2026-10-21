"""Unit tests for artifact publication store."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact import Artifact
from app.services.hosting.publication_store import (
    get_publication,
    list_publications,
    list_publications_for_artifacts,
    publication_to_dict,
    upsert_publication,
)
from app.services.hosting.targets import LEGACY_VERCEL_TARGET_ID


@pytest.mark.asyncio
async def test_upsert_and_get_publication(db_session: AsyncSession) -> None:
    artifact_id = str(uuid.uuid4())
    db_session.add(Artifact(id=artifact_id, name="page.html"))
    await db_session.commit()

    row = await upsert_publication(
        db_session,
        artifact_id=artifact_id,
        hosting_target_id=LEGACY_VERCEL_TARGET_ID,
        publication_url="https://live.example.com",
        publication_status="READY",
        publication_project_ref="prj_1",
        publication_version_id="ver_1",
    )
    assert row.id
    loaded = await get_publication(db_session, artifact_id, LEGACY_VERCEL_TARGET_ID)
    assert loaded is not None
    assert loaded.publication_url == "https://live.example.com"


@pytest.mark.asyncio
async def test_upsert_updates_existing_publication(db_session: AsyncSession) -> None:
    artifact_id = str(uuid.uuid4())
    db_session.add(Artifact(id=artifact_id, name="page.html"))
    await db_session.commit()

    await upsert_publication(
        db_session,
        artifact_id=artifact_id,
        hosting_target_id=LEGACY_VERCEL_TARGET_ID,
        publication_url="https://v1.example.com",
        publication_status="READY",
        publication_project_ref="prj_1",
        publication_version_id="ver_1",
    )
    updated = await upsert_publication(
        db_session,
        artifact_id=artifact_id,
        hosting_target_id=LEGACY_VERCEL_TARGET_ID,
        publication_url="https://v2.example.com",
        publication_status="READY",
        publication_project_ref="prj_1",
        publication_version_id="ver_2",
    )
    assert updated.publication_url == "https://v2.example.com"
    pubs = await list_publications(db_session, artifact_id)
    assert len(pubs) == 1


@pytest.mark.asyncio
async def test_list_publications_for_artifacts_batch(db_session: AsyncSession) -> None:
    art_a = str(uuid.uuid4())
    art_b = str(uuid.uuid4())
    db_session.add(Artifact(id=art_a, name="a.html"))
    db_session.add(Artifact(id=art_b, name="b.html"))
    await db_session.commit()
    await upsert_publication(
        db_session,
        artifact_id=art_a,
        hosting_target_id=LEGACY_VERCEL_TARGET_ID,
        publication_url="https://a.example.com",
        publication_status="READY",
        publication_project_ref=None,
        publication_version_id="v1",
    )
    grouped = await list_publications_for_artifacts(db_session, [art_a, art_b])
    assert len(grouped[art_a]) == 1
    assert grouped[art_b] == []


def test_publication_to_dict_includes_target_name() -> None:
    from app.database.models.artifact_publication import ArtifactPublication

    row = ArtifactPublication(
        id="pub-1",
        artifact_id="art-1",
        hosting_target_id="t1",
        publication_url="https://x.example.com",
        publication_status="READY",
    )
    data = publication_to_dict(row, hosting_target_name="Prod Vercel")
    assert data["hosting_target_name"] == "Prod Vercel"


@pytest.mark.asyncio
async def test_list_publications_for_artifacts_empty_input(db_session: AsyncSession) -> None:
    assert await list_publications_for_artifacts(db_session, []) == {}
