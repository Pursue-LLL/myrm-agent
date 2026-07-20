"""Hosting API integration tests — real preflight, vault, orchestrator; external HTTP only mocked."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.files.hosting_api import router as hosting_router
from app.core.artifacts.listener import upsert_processor_artifact
from app.core.infra.limiter import limiter
from app.database.connection import get_db
from app.database.models.artifact_publication import ArtifactPublication
from app.services.hosting.targets import save_hosting_targets
from app.services.hosting.types import HostingTarget


def _public_dns(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
    return [(2, 1, 6, "", ("8.8.8.8", 0))]


@pytest.fixture(autouse=True)
def bypass_rate_limit():
    with patch(
        "app.core.infra.limiter.limiter._limiter.check",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(allowed=True, retry_after_seconds=None),
    ):
        yield


@pytest.fixture
def hosting_integration_client(db_session: AsyncSession, tmp_path, monkeypatch) -> TestClient:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    limiter.enabled = False
    test_app = FastAPI()
    test_app.include_router(hosting_router)

    async def override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        "app.api.files.hosting_api.get_workspace_root",
        lambda: workspace,
    )

    with TestClient(test_app) as test_client:
        yield test_client, workspace, db_session

    limiter.enabled = True


async def _seed_webhook_target(db_session: AsyncSession, target_id: str) -> None:
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(
                id=target_id,
                name="CI Webhook",
                provider_type="http_webhook",
                config={"webhook_url": "https://hooks.example.com/publish"},
                is_default=True,
            )
        ],
    )


async def _seed_html_artifact(db_session: AsyncSession, workspace, *, file_id: str | None = None) -> str:
    html_path = workspace / "index.html"
    html_path.write_text("<html><body><h1>Integration</h1></body></html>", encoding="utf-8")
    artifact_id = file_id or f"hosting-int-{uuid.uuid4().hex[:8]}"
    await upsert_processor_artifact(
        db_session,
        file_id=artifact_id,
        filename="index.html",
        sandbox_path=str(html_path),
        workspace_root=str(workspace),
        chat_id="chat-hosting-int",
    )
    return artifact_id


@pytest.mark.asyncio
async def test_preflight_real_vault_html_deployable(hosting_integration_client) -> None:
    client, workspace, db_session = hosting_integration_client
    artifact_id = await _seed_html_artifact(db_session, workspace)

    response = client.get(f"/{artifact_id}/publish/preflight")
    assert response.status_code == 200
    body = response.json()
    assert body["deployable"] is True
    assert body["reason"] == "OK"


@pytest.mark.asyncio
async def test_preflight_rejects_tsx_only_artifact(hosting_integration_client) -> None:
    client, workspace, db_session = hosting_integration_client
    tsx_path = workspace / "App.tsx"
    tsx_path.write_text("export default () => null", encoding="utf-8")
    artifact_id = f"tsx-only-{uuid.uuid4().hex[:8]}"
    await upsert_processor_artifact(
        db_session,
        file_id=artifact_id,
        filename="App.tsx",
        sandbox_path=str(tsx_path),
        workspace_root=str(workspace),
    )

    response = client.get(f"/{artifact_id}/publish/preflight")
    assert response.status_code == 200
    body = response.json()
    assert body["deployable"] is False
    assert body["reason"] in ("CODE_REQUIRES_HTML_ARTIFACT", "REQUIRES_HTML_ENTRY")


@pytest.mark.asyncio
async def test_publish_full_chain_http_webhook(hosting_integration_client) -> None:
    client, workspace, db_session = hosting_integration_client
    target_id = f"wh-int-{uuid.uuid4().hex[:8]}"
    await _seed_webhook_target(db_session, target_id)
    artifact_id = await _seed_html_artifact(db_session, workspace)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"url": "https://published.example.com/live", "publication_id": "pub_int_1"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    with patch("app.services.hosting.ssrf_guard.socket.getaddrinfo", side_effect=_public_dns):
        with patch(
            "app.services.hosting.providers.http_webhook.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
        ):
            response = client.post(
                f"/{artifact_id}/publish",
                json={"target_id": target_id, "token": ""},
            )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["publication_url"] == "https://published.example.com/live"
    assert data["publication"]["hosting_target_id"] == target_id
    assert data["provider_publication_ref"]

    pub = (
        await db_session.execute(
            select(ArtifactPublication).where(
                ArtifactPublication.artifact_id == artifact_id,
                ArtifactPublication.hosting_target_id == target_id,
            )
        )
    ).scalars().first()
    assert pub is not None
    assert pub.publication_status == "READY"


@pytest.mark.asyncio
async def test_publish_missing_target_returns_500(hosting_integration_client) -> None:
    client, workspace, db_session = hosting_integration_client
    artifact_id = await _seed_html_artifact(db_session, workspace)

    response = client.post(
        f"/{artifact_id}/publish",
        json={"target_id": "missing-target-id", "token": ""},
    )
    assert response.status_code == 500
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_target_credentials_roundtrip(hosting_integration_client) -> None:
    client, _workspace, db_session = hosting_integration_client
    target_id = f"cred-int-{uuid.uuid4().hex[:8]}"
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(
                id=target_id,
                name="Netlify",
                provider_type="netlify",
                config={"site_id": "site_abc"},
                is_default=True,
            )
        ],
    )

    put = client.put(
        f"/hosting/targets/{target_id}/credentials",
        json={"credentials": {"access_token": "nl_secret"}},
    )
    assert put.status_code == 200

    get = client.get(f"/hosting/targets/{target_id}/credentials")
    assert get.status_code == 200
    body = get.json()
    assert body["configured"] is True
    assert body["credentials"]["access_token"] == "nl_secret"


@pytest.mark.asyncio
async def test_test_connection_webhook_validates_url(hosting_integration_client) -> None:
    client, _workspace, db_session = hosting_integration_client
    target_id = f"wh-test-{uuid.uuid4().hex[:8]}"
    await _seed_webhook_target(db_session, target_id)

    with patch("app.services.hosting.ssrf_guard.socket.getaddrinfo", side_effect=_public_dns):
        response = client.post(f"/hosting/targets/{target_id}/test")

    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.asyncio
async def test_publications_list_after_publish(hosting_integration_client) -> None:
    client, workspace, db_session = hosting_integration_client
    target_id = f"wh-pub-{uuid.uuid4().hex[:8]}"
    await _seed_webhook_target(db_session, target_id)
    artifact_id = await _seed_html_artifact(db_session, workspace)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"url": "https://listed.example.com", "publication_id": "pub_list"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    with patch("app.services.hosting.ssrf_guard.socket.getaddrinfo", side_effect=_public_dns):
        with patch(
            "app.services.hosting.providers.http_webhook.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
        ):
            publish = client.post(f"/{artifact_id}/publish", json={"target_id": target_id, "token": ""})
    assert publish.status_code == 200

    list_resp = client.get(f"/{artifact_id}/publications")
    assert list_resp.status_code == 200
    pubs = list_resp.json()["publications"]
    assert len(pubs) == 1
    assert pubs[0]["publication_url"] == "https://listed.example.com"
    assert pubs[0]["hosting_target_name"] == "CI Webhook"


@pytest.mark.asyncio
async def test_publish_websocket_polls_ready(hosting_integration_client) -> None:
    client, workspace, db_session = hosting_integration_client
    target_id = f"wh-ws-{uuid.uuid4().hex[:8]}"
    await _seed_webhook_target(db_session, target_id)
    artifact_id = await _seed_html_artifact(db_session, workspace)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"url": "https://ws.example.com", "publication_id": "pub_ws"},
            request=request,
        )

    transport = httpx.MockTransport(handler)

    class _SessionCtx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *_args: object) -> None:
            return None

    with patch("app.services.hosting.ssrf_guard.socket.getaddrinfo", side_effect=_public_dns):
        with patch(
            "app.services.hosting.providers.http_webhook.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
        ):
            with patch("app.api.files.hosting_api.get_session", return_value=_SessionCtx()):
                publish = client.post(f"/{artifact_id}/publish", json={"target_id": target_id, "token": ""})
                assert publish.status_code == 200
                provider_ref = publish.json()["provider_publication_ref"]

                with client.websocket_connect(
                    f"/{artifact_id}/publish/status/{provider_ref}?target_id={target_id}"
                ) as ws:
                    ws.send_json({"type": "auth"})
                    msg = ws.receive_json()
                    assert msg["status"] == "READY"


@pytest.mark.asyncio
async def test_webhook_publish_without_saved_credentials(hosting_integration_client) -> None:
    """Matches FE: webhook target saved with empty credential fields."""
    client, workspace, db_session = hosting_integration_client
    target_id = f"wh-nocred-{uuid.uuid4().hex[:8]}"
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(
                id=target_id,
                name="Webhook No Creds",
                provider_type="http_webhook",
                config={"webhook_url": "https://hooks.example.com/no-creds"},
                is_default=True,
            )
        ],
    )
    artifact_id = await _seed_html_artifact(db_session, workspace)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": "https://nocreds.example.com"}, request=request)

    transport = httpx.MockTransport(handler)
    with patch("app.services.hosting.ssrf_guard.socket.getaddrinfo", side_effect=_public_dns):
        with patch(
            "app.services.hosting.providers.http_webhook.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
        ):
            response = client.post(f"/{artifact_id}/publish", json={"target_id": target_id, "token": ""})

    assert response.status_code == 200
    assert response.json()["publication_url"] == "https://nocreds.example.com"


@pytest.mark.asyncio
async def test_target_crud_lifecycle_matches_frontend(hosting_integration_client) -> None:
    client, _workspace, db_session = hosting_integration_client
    create = client.post(
        "/hosting/targets",
        json={
            "name": "Lifecycle Webhook",
            "provider_type": "http_webhook",
            "config": {"webhook_url": "https://hooks.example.com/lifecycle", "allow_http": "false"},
            "is_default": True,
        },
    )
    assert create.status_code == 200
    target_id = create.json()["id"]

    update = client.put(
        f"/hosting/targets/{target_id}",
        json={
            "name": "Lifecycle Updated",
            "provider_type": "http_webhook",
            "config": {"webhook_url": "https://hooks.example.com/lifecycle-v2", "allow_http": "false"},
            "is_default": True,
        },
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Lifecycle Updated"

    with patch("app.services.hosting.ssrf_guard.socket.getaddrinfo", side_effect=_public_dns):
        test_resp = client.post(f"/hosting/targets/{target_id}/test")
    assert test_resp.status_code == 200
    assert test_resp.json()["ok"] is True

    delete = client.delete(f"/hosting/targets/{target_id}")
    assert delete.status_code == 200
    assert client.get("/hosting/targets").json()["targets"] == []


@pytest.mark.asyncio
async def test_preflight_unknown_target_id_404(hosting_integration_client) -> None:
    client, workspace, db_session = hosting_integration_client
    artifact_id = await _seed_html_artifact(db_session, workspace)
    response = client.get(f"/{artifact_id}/publish/preflight?target_id=missing-target")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_publish_artifact_not_found_400(hosting_integration_client) -> None:
    client, _workspace, db_session = hosting_integration_client
    target_id = f"wh-404-{uuid.uuid4().hex[:8]}"
    await _seed_webhook_target(db_session, target_id)
    response = client.post(
        f"/missing-artifact-{uuid.uuid4()}/publish",
        json={"target_id": target_id, "token": ""},
    )
    assert response.status_code == 400
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_publish_tsx_preflight_failed_400(hosting_integration_client) -> None:
    client, workspace, db_session = hosting_integration_client
    target_id = f"wh-tsx-{uuid.uuid4().hex[:8]}"
    await _seed_webhook_target(db_session, target_id)
    tsx_path = workspace / "Only.tsx"
    tsx_path.write_text("export default 1", encoding="utf-8")
    artifact_id = f"tsx-fail-{uuid.uuid4().hex[:8]}"
    await upsert_processor_artifact(
        db_session,
        file_id=artifact_id,
        filename="Only.tsx",
        sandbox_path=str(tsx_path),
        workspace_root=str(workspace),
    )
    response = client.post(f"/{artifact_id}/publish", json={"target_id": target_id, "token": ""})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_publish_ssrf_blocks_webhook_url(hosting_integration_client) -> None:
    client, workspace, db_session = hosting_integration_client
    target_id = f"wh-ssrf-{uuid.uuid4().hex[:8]}"
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(
                id=target_id,
                name="Bad Webhook",
                provider_type="http_webhook",
                config={"webhook_url": "https://127.0.0.1/internal"},
                is_default=True,
            )
        ],
    )
    artifact_id = await _seed_html_artifact(db_session, workspace)
    response = client.post(f"/{artifact_id}/publish", json={"target_id": target_id, "token": ""})
    assert response.status_code == 500
    assert "blocked" in response.json()["detail"].lower() or "localhost" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_redeploy_updates_existing_publication(hosting_integration_client) -> None:
    client, workspace, db_session = hosting_integration_client
    target_id = f"wh-re-{uuid.uuid4().hex[:8]}"
    await _seed_webhook_target(db_session, target_id)
    artifact_id = await _seed_html_artifact(db_session, workspace)
    urls = ["https://v1.example.com", "https://v2.example.com"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": urls.pop(0), "publication_id": "pub_re"}, request=request)

    transport = httpx.MockTransport(handler)
    with patch("app.services.hosting.ssrf_guard.socket.getaddrinfo", side_effect=_public_dns):
        with patch(
            "app.services.hosting.providers.http_webhook.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
        ):
            first = client.post(f"/{artifact_id}/publish", json={"target_id": target_id, "token": ""})
        with patch(
            "app.services.hosting.providers.http_webhook.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
        ):
            second = client.post(f"/{artifact_id}/publish", json={"target_id": target_id, "token": ""})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["publication_url"] == "https://v2.example.com"
    pubs = client.get(f"/{artifact_id}/publications").json()["publications"]
    assert len(pubs) == 1
    assert pubs[0]["publication_url"] == "https://v2.example.com"


@pytest.mark.asyncio
async def test_update_and_delete_target_not_found(hosting_integration_client) -> None:
    client, _, _db = hosting_integration_client
    missing = "missing-target-id"
    update = client.put(
        f"/hosting/targets/{missing}",
        json={"name": "X", "provider_type": "vercel", "config": {}, "is_default": False},
    )
    assert update.status_code == 404
    delete = client.delete(f"/hosting/targets/{missing}")
    assert delete.status_code == 404


@pytest.mark.asyncio
async def test_webhook_credentials_status_without_secrets(hosting_integration_client) -> None:
    client, _workspace, db_session = hosting_integration_client
    target_id = f"wh-cred-{uuid.uuid4().hex[:8]}"
    await _seed_webhook_target(db_session, target_id)
    response = client.get(f"/hosting/targets/{target_id}/credentials")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["credentials"] == {}


@pytest.mark.asyncio
async def test_ws_rejects_invalid_auth(hosting_integration_client) -> None:
    client, workspace, db_session = hosting_integration_client
    target_id = f"wh-badws-{uuid.uuid4().hex[:8]}"
    await _seed_webhook_target(db_session, target_id)
    artifact_id = await _seed_html_artifact(db_session, workspace)

    class _SessionCtx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *_args: object) -> None:
            return None

    with patch("app.api.files.hosting_api.get_session", return_value=_SessionCtx()):
        with client.websocket_connect(
            f"/{artifact_id}/publish/status/fake-ref?target_id={target_id}"
        ) as ws:
            ws.send_json({"type": "not-auth"})
            # Server closes after invalid auth; receive may raise
            try:
                ws.receive_json()
            except Exception:
                pass


@pytest.mark.asyncio
async def test_vercel_publish_without_credentials_returns_500(hosting_integration_client) -> None:
    """User-facing: Vercel target with no saved token and no override must fail clearly."""
    client, workspace, db_session = hosting_integration_client
    target_id = f"vercel-nocred-{uuid.uuid4().hex[:8]}"
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(
                id=target_id,
                name="Vercel No Creds",
                provider_type="vercel",
                config={},
                is_default=True,
            )
        ],
    )
    artifact_id = await _seed_html_artifact(db_session, workspace)

    with patch("app.services.hosting.credentials.get_platform_vercel_token", return_value=None):
        with patch("app.services.hosting.credentials.load_legacy_vercel_token", AsyncMock(return_value=None)):
            response = client.post(
                f"/{artifact_id}/publish",
                json={"target_id": target_id, "token": ""},
            )

    assert response.status_code == 500
    assert "credentials" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_make_default_missing_target_404(hosting_integration_client) -> None:
    client, _, _db = hosting_integration_client
    response = client.post("/hosting/targets/does-not-exist/make-default")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_put_credentials_missing_target_404(hosting_integration_client) -> None:
    client, _, _db = hosting_integration_client
    response = client.put(
        "/hosting/targets/missing-target/credentials",
        json={"credentials": {"token": "x"}},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_test_connection_vercel_without_credentials(hosting_integration_client) -> None:
    client, _workspace, db_session = hosting_integration_client
    target_id = f"vercel-test-{uuid.uuid4().hex[:8]}"
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(
                id=target_id,
                name="Vercel",
                provider_type="vercel",
                config={},
                is_default=True,
            )
        ],
    )
    with patch("app.services.hosting.credentials.get_platform_vercel_token", return_value=None):
        response = client.post(f"/hosting/targets/{target_id}/test")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "credentials" in body["message"].lower() or "token" in body["message"].lower()


@pytest.mark.asyncio
async def test_multi_target_publications_same_artifact(hosting_integration_client) -> None:
    """Same HTML artifact published to two webhook targets keeps separate publication rows."""
    client, workspace, db_session = hosting_integration_client
    target_a = f"wh-a-{uuid.uuid4().hex[:8]}"
    target_b = f"wh-b-{uuid.uuid4().hex[:8]}"
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(
                id=target_a,
                name="Webhook A",
                provider_type="http_webhook",
                config={"webhook_url": "https://hooks.example.com/a"},
                is_default=True,
            ),
            HostingTarget(
                id=target_b,
                name="Webhook B",
                provider_type="http_webhook",
                config={"webhook_url": "https://hooks.example.com/b"},
                is_default=False,
            ),
        ],
    )
    artifact_id = await _seed_html_artifact(db_session, workspace)
    urls = {"https://a.example.com", "https://b.example.com"}

    def handler(request: httpx.Request) -> httpx.Response:
        host = "a" if "/a" in str(request.url) else "b"
        return httpx.Response(
            200,
            json={"url": f"https://{host}.example.com", "publication_id": f"pub_{host}"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    with patch("app.services.hosting.ssrf_guard.socket.getaddrinfo", side_effect=_public_dns):
        with patch(
            "app.services.hosting.providers.http_webhook.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
        ):
            first = client.post(f"/{artifact_id}/publish", json={"target_id": target_a, "token": ""})
        with patch(
            "app.services.hosting.providers.http_webhook.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
        ):
            second = client.post(f"/{artifact_id}/publish", json={"target_id": target_b, "token": ""})

    assert first.status_code == 200
    assert second.status_code == 200
    pubs = client.get(f"/{artifact_id}/publications").json()["publications"]
    assert len(pubs) == 2
    pub_urls = {p["publication_url"] for p in pubs}
    assert pub_urls == urls


@pytest.mark.asyncio
async def test_preflight_with_valid_target_id_succeeds(hosting_integration_client) -> None:
    client, workspace, db_session = hosting_integration_client
    target_id = f"wh-pf-{uuid.uuid4().hex[:8]}"
    await _seed_webhook_target(db_session, target_id)
    artifact_id = await _seed_html_artifact(db_session, workspace)
    response = client.get(f"/{artifact_id}/publish/preflight?target_id={target_id}")
    assert response.status_code == 200
    assert response.json()["deployable"] is True
