"""Integration tests for WeChat Official Account draft API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("app.api.channels.wechat_official", reason="Backend import issues")


@asynccontextmanager
async def _noop_lifespan(app):
    yield


@pytest.fixture(scope="module")
def client() -> TestClient:
    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="channels_local")
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.router.lifespan_context = original_lifespan


def test_wechat_official_draft_requires_credentials(client: TestClient, tmp_path: Path) -> None:
    html_file = tmp_path / "article.wechat.html"
    html_file.write_text("<html><body><p>Hi</p></body></html>", encoding="utf-8")
    with patch("app.api.channels.wechat_official._get_workspace_root", return_value=str(tmp_path)):
        response = client.post(
            "/api/v1/channels/manage/wechat-official/draft",
            json={"htmlPath": str(html_file), "title": "Test"},
        )
    assert response.status_code == 400
    assert "credentials" in response.json()["detail"].lower()


def test_wechat_official_test_rejects_empty_secret(client: TestClient) -> None:
    response = client.post(
        "/api/v1/channels/manage/wechat-official/test",
        json={"appId": "wx_test", "appSecret": ""},
    )
    assert response.status_code == 422


def test_wechat_official_draft_fail_closed_without_workspace(client: TestClient, tmp_path: Path) -> None:
    html_file = tmp_path / "article.wechat.html"
    html_file.write_text("<html><body><p>Hi</p></body></html>", encoding="utf-8")
    with patch("app.api.channels.wechat_official._get_workspace_root", return_value=None):
        response = client.post(
            "/api/v1/channels/manage/wechat-official/draft",
            json={"htmlPath": str(html_file), "title": "Test"},
        )
    assert response.status_code == 503
    assert "workspace root unavailable" in response.json()["detail"].lower()


def test_wechat_official_draft_rejects_path_outside_workspace(
    client: TestClient,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.wechat.html"
    outside.write_text("<html><body><p>Outside</p></body></html>", encoding="utf-8")

    with patch("app.api.channels.wechat_official._get_workspace_root", return_value=str(workspace)):
        response = client.post(
            "/api/v1/channels/manage/wechat-official/draft",
            json={"htmlPath": str(outside), "title": "Test"},
        )
    assert response.status_code == 403
    assert "access denied" in response.json()["detail"].lower()


def test_wechat_official_draft_rejects_workspace_prefix_trap(
    client: TestClient,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    trap_dir = tmp_path / "workspace-evil"
    trap_dir.mkdir()
    trapped = trap_dir / "secret.wechat.html"
    trapped.write_text("<html><body><p>Trap</p></body></html>", encoding="utf-8")

    with patch("app.api.channels.wechat_official._get_workspace_root", return_value=str(workspace)):
        response = client.post(
            "/api/v1/channels/manage/wechat-official/draft",
            json={"htmlPath": str(trapped), "title": "Test"},
        )
    assert response.status_code == 403
    assert "access denied" in response.json()["detail"].lower()


def test_wechat_official_draft_returns_compliance_warnings_on_success(
    client: TestClient,
    tmp_path: Path,
) -> None:
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n")
    html_file = tmp_path / "wellness.wechat.html"
    html_file.write_text(
        '<html><body><p>这款茶能排毒养颜</p><img src="cover.png" alt="cover"></body></html>',
        encoding="utf-8",
    )
    with (
        patch("app.api.channels.wechat_official._get_workspace_root", return_value=str(tmp_path)),
        patch(
            "app.api.channels.wechat_official._load_official_credentials",
            new=AsyncMock(return_value={"appId": "wx_test", "appSecret": "secret_test"}),
        ),
        patch(
            "app.channels.providers.wechat.wechat_api_client.WeChatOfficialApiClient.post_multipart",
            new=AsyncMock(
                side_effect=[
                    {"url": "https://mmbiz.qpic.cn/content-img"},
                    {"media_id": "thumb_media_123"},
                ]
            ),
        ),
        patch(
            "app.channels.providers.wechat.wechat_api_client.WeChatOfficialApiClient.post_json",
            new=AsyncMock(return_value={"media_id": "draft_media_456"}),
        ),
        patch(
            "app.channels.providers.wechat.wechat_api_client.WeChatOfficialApiClient.ensure_token",
            new=AsyncMock(return_value="token_test"),
        ),
        patch(
            "app.channels.providers.wechat.wechat_api_client.WeChatOfficialApiClient.close",
            new=AsyncMock(),
        ),
    ):
        response = client.post(
            "/api/v1/channels/manage/wechat-official/draft",
            json={"htmlPath": str(html_file), "title": "Wellness"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["mediaId"] == "draft_media_456"
    assert len(body["complianceWarnings"]) == 1
    assert body["complianceWarnings"][0]["category"] == "medical_efficacy"
    assert body["complianceWarnings"][0]["highRisk"] is False
    assert "排毒" in body["complianceWarnings"][0]["terms"]


def test_wechat_official_draft_blocks_high_risk_compliance(
    client: TestClient,
    tmp_path: Path,
) -> None:
    html_file = tmp_path / "risky.wechat.html"
    html_file.write_text(
        "<html><body><p>集赞 20 个送礼品，分享到朋友圈解锁全文</p></body></html>",
        encoding="utf-8",
    )
    with (
        patch("app.api.channels.wechat_official._get_workspace_root", return_value=str(tmp_path)),
        patch(
            "app.api.channels.wechat_official._load_official_credentials",
            new=AsyncMock(return_value={"appId": "wx_test", "appSecret": "secret_test"}),
        ),
    ):
        response = client.post(
            "/api/v1/channels/manage/wechat-official/draft",
            json={"htmlPath": str(html_file), "title": "Risky"},
        )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "wechat_compliance_blocked"
    assert "集赞" in detail["message"]
    assert isinstance(detail["hits"], list)
    assert detail["hits"][0]["highRisk"] is True
    assert "集赞" in detail["hits"][0]["terms"]
