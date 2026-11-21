"""A share serves the version its token pins; the deploy-file resolver honours an explicit version."""

from __future__ import annotations

import shutil
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.artifacts.share.share_bundle import (
    bundle_asset_count,
    bundle_dir_for_claims,
)
from app.services.artifacts.share.share_token import (
    parse_artifact_share_token,
)
from app.services.hosting.packager import PublishFile
from tests.support.detached_artifact import make_detached_artifact

pytestmark = pytest.mark.usefixtures("chats_share_workspace")


@pytest.mark.asyncio
async def test_share_rematerialization_uses_pinned_version(share_client, html_artifact) -> None:
    """Verify that bundle re-materialization passes version_id from JWT claims."""
    files_v1 = {
        "index.html": PublishFile(path="index.html", content="<html>v1</html>", encoding="utf-8"),
    }
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files_v1),
    ) as mock_resolve:
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
        assert response.status_code == 200
        assert mock_resolve.call_count == 1
        _, kwargs = mock_resolve.call_args
        assert "version_id" in kwargs
        assert kwargs["version_id"] is not None

    token = response.json()["token"]
    claims = parse_artifact_share_token(token)
    assert claims is not None

    assert bundle_asset_count(claims) == 1

    shutil.rmtree(bundle_dir_for_claims(claims), ignore_errors=True)
    assert bundle_asset_count(claims) == 0

    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, files_v1),
    ) as mock_resolve_again:
        serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
        assert serve.status_code == 200
        _, kwargs2 = mock_resolve_again.call_args
        assert kwargs2["version_id"] == claims.version_id


@pytest.mark.asyncio
async def test_share_version_pinning_integration(share_client, db_session, workspace) -> None:
    """Integration: full share→delete→re-materialize chain with real vault, no key-path mocks."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(workspace))
    v1_uri = vault.put("<html>v1</html>", "index.html")
    v2_uri = vault.put("<html>v2-latest</html>", "index.html")

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="index.html",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()

    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=v1_uri,
        sha256_hash="h1",
    )
    db_session.add(ver1)
    await db_session.commit()

    import asyncio

    await asyncio.sleep(0.05)

    ver2 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=v2_uri,
        sha256_hash="h2",
    )
    db_session.add(ver2)
    await db_session.commit()
    await db_session.refresh(artifact)

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        response = share_client.post(
            f"/{artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["version_id"] == ver2.id

    token = payload["token"]
    claims = parse_artifact_share_token(token)
    assert claims is not None

    first_serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert first_serve.status_code == 200
    assert "v2-latest" in first_serve.text

    shutil.rmtree(bundle_dir_for_claims(claims), ignore_errors=True)
    assert bundle_asset_count(claims) == 0

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        re_serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert re_serve.status_code == 200
    assert "v2-latest" in re_serve.text


@pytest.mark.asyncio
async def test_share_pinned_version_survives_new_version(share_client, db_session, workspace) -> None:
    """Share pins v1, then v2 is added; re-materialization still serves v1 content."""
    from datetime import datetime, timedelta

    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(workspace))
    v1_uri = vault.put("<html>v1-pinned</html>", "index.html")

    art_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    t1 = datetime(2025, 1, 1)

    artifact = Artifact(id=art_id, name="index.html", chat_id=chat_id, is_deleted=False)
    db_session.add(artifact)
    await db_session.commit()

    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=art_id,
        vault_uri=v1_uri,
        sha256_hash="h1",
    )
    db_session.add(ver1)
    await db_session.commit()
    await db_session.refresh(artifact)

    detached_v1_only = make_detached_artifact(
        artifact_id=art_id,
        name="index.html",
        chat_id=chat_id,
        versions=[ver1],
    )
    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached_v1_only,
    ):
        response = share_client.post(
            f"/{artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    assert response.json()["version_id"] == ver1.id
    token = response.json()["token"]

    v2_uri = vault.put("<html>v2-newer</html>", "index.html")
    ver2 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=art_id,
        vault_uri=v2_uri,
        sha256_hash="h2",
        created_at=t1 + timedelta(hours=1),
    )
    db_session.add(ver2)
    await db_session.commit()

    claims = parse_artifact_share_token(token)
    assert claims is not None
    shutil.rmtree(bundle_dir_for_claims(claims), ignore_errors=True)

    detached_both = make_detached_artifact(
        artifact_id=art_id,
        name="index.html",
        chat_id=chat_id,
        versions=[ver1, ver2],
    )
    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached_both,
    ):
        re_serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert re_serve.status_code == 200
    assert "v1-pinned" in re_serve.text
    assert "v2-newer" not in re_serve.text


@pytest.mark.asyncio
async def test_share_invalid_version_returns_404(share_client, db_session, workspace) -> None:
    """Re-materialization with a deleted/invalid version_id returns 404."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    vault = ArtifactVault(str(workspace))
    v1_uri = vault.put("<html>v1</html>", "index.html")

    artifact = Artifact(
        id=str(uuid.uuid4()),
        name="index.html",
        chat_id=str(uuid.uuid4()),
        is_deleted=False,
    )
    db_session.add(artifact)
    await db_session.commit()
    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=v1_uri,
        sha256_hash="h1",
    )
    db_session.add(ver1)
    await db_session.commit()
    await db_session.refresh(artifact)

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact,
    ):
        response = share_client.post(
            f"/{artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html"},
        )
    assert response.status_code == 200
    token = response.json()["token"]

    claims = parse_artifact_share_token(token)
    assert claims is not None
    shutil.rmtree(bundle_dir_for_claims(claims), ignore_errors=True)

    artifact_no_ver = Artifact(id=artifact.id, name="index.html", chat_id=artifact.chat_id, is_deleted=False)
    artifact_no_ver.versions = []

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=artifact_no_ver,
    ):
        re_serve = share_client.get(f"/public/artifact-share/{token}", follow_redirects=False)
    assert re_serve.status_code == 404


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_version_id_none_uses_latest(db_session, workspace) -> None:
    """When version_id=None, resolve_artifact_deploy_files picks the latest version."""
    from datetime import datetime, timedelta

    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    from app.services.hosting.artifact_files import resolve_artifact_deploy_files

    vault = ArtifactVault(str(workspace))
    v1_uri = vault.put("<html>old</html>", "index.html")
    v2_uri = vault.put("<html>new-latest</html>", "index.html")

    art_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    t1 = datetime(2025, 1, 1)
    t2 = t1 + timedelta(hours=1)

    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=art_id,
        vault_uri=v1_uri,
        sha256_hash="h1",
        created_at=t1,
    )
    ver2 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=art_id,
        vault_uri=v2_uri,
        sha256_hash="h2",
        created_at=t2,
    )

    detached = make_detached_artifact(artifact_id=art_id, name="index.html", chat_id=chat_id, versions=[ver1, ver2])

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        _, files = await resolve_artifact_deploy_files(db_session, art_id, str(workspace))

    import base64

    raw = next(iter(files.values())).content
    decoded = base64.b64decode(raw).decode() if ";" not in raw and "/" not in raw else raw
    assert "new-latest" in decoded


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_explicit_version(db_session, workspace) -> None:
    """When version_id is given, resolve_artifact_deploy_files picks that exact version."""
    from datetime import datetime, timedelta

    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    from app.services.hosting.artifact_files import resolve_artifact_deploy_files

    vault = ArtifactVault(str(workspace))
    v1_uri = vault.put("<html>first</html>", "index.html")
    v2_uri = vault.put("<html>second</html>", "index.html")

    art_id = str(uuid.uuid4())
    chat_id = str(uuid.uuid4())
    t1 = datetime(2025, 1, 1)
    t2 = t1 + timedelta(hours=1)

    ver1 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=art_id,
        vault_uri=v1_uri,
        sha256_hash="h1",
        created_at=t1,
    )
    ver2 = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=art_id,
        vault_uri=v2_uri,
        sha256_hash="h2",
        created_at=t2,
    )

    detached = make_detached_artifact(artifact_id=art_id, name="index.html", chat_id=chat_id, versions=[ver1, ver2])

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        _, files_v1 = await resolve_artifact_deploy_files(db_session, art_id, str(workspace), version_id=ver1.id)
    raw_v1 = next(iter(files_v1.values())).content
    # Vault object is extension-less but named from artifact.name (index.html),
    # so the HTML payload is stored as UTF-8 text rather than base64.
    assert "first" in raw_v1

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        _, files_v2 = await resolve_artifact_deploy_files(db_session, art_id, str(workspace), version_id=ver2.id)
    raw_v2 = next(iter(files_v2.values())).content
    assert "second" in raw_v2


@pytest.mark.asyncio
async def test_resolve_artifact_deploy_files_invalid_version_raises(db_session, workspace) -> None:
    """When version_id doesn't match any version, LookupError is raised."""
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    from app.services.hosting.artifact_files import resolve_artifact_deploy_files

    vault = ArtifactVault(str(workspace))
    v1_uri = vault.put("<html>only</html>", "index.html")

    art_id = str(uuid.uuid4())
    ver1 = ArtifactVersion(id=str(uuid.uuid4()), artifact_id=art_id, vault_uri=v1_uri, sha256_hash="h1")
    detached = make_detached_artifact(
        artifact_id=art_id,
        name="index.html",
        chat_id=str(uuid.uuid4()),
        versions=[ver1],
    )

    with patch(
        "app.services.hosting.artifact_files.ensure_artifact_for_deploy",
        new_callable=AsyncMock,
        return_value=detached,
    ):
        with pytest.raises(LookupError, match="not found"):
            await resolve_artifact_deploy_files(db_session, art_id, str(workspace), version_id="nonexistent-id")
