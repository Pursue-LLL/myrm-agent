"""Integration: WeChat Official HITL draft — real compliance + draft_service wiring.

External WeChat HTTP is stubbed only at ``WeChatOfficialApiClient`` boundary;
compliance scan, digest SSOT, image rewrite, and API routing are unmocked.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.channels.providers.wechat.draft_service import WeChatDraftService
from app.channels.providers.wechat.wechat_api_client import WeChatOfficialApiClient
from app.services.compliance.wechat_compliance_scan import WeChatComplianceBlockedError


@asynccontextmanager
async def _noop_lifespan(app: object):
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


@pytest.mark.integration
def test_api_draft_compliance_blocks_before_wechat_api(client: TestClient, tmp_path: Path) -> None:
    html_file = tmp_path / "blocked.wechat.html"
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
        patch(
            "app.channels.providers.wechat.wechat_api_client.WeChatOfficialApiClient.post_multipart",
            new=AsyncMock(),
        ) as mock_multipart,
        patch(
            "app.channels.providers.wechat.wechat_api_client.WeChatOfficialApiClient.post_json",
            new=AsyncMock(),
        ) as mock_json,
    ):
        response = client.post(
            "/api/v1/channels/manage/wechat-official/draft",
            json={"htmlPath": str(html_file), "title": "Blocked Article"},
        )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "wechat_compliance_blocked"
    assert "集赞" in detail["message"]
    mock_multipart.assert_not_called()
    mock_json.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_draft_service_blocks_high_risk_before_image_upload(tmp_path: Path) -> None:
    html_path = tmp_path / "risky.html"
    html_path.write_text(
        "<html><body><p>保本理财，稳赚不赔</p></body></html>",
        encoding="utf-8",
    )
    client = AsyncMock(spec=WeChatOfficialApiClient)
    service = WeChatDraftService(client)

    with pytest.raises(WeChatComplianceBlockedError):
        await service.create_draft_from_html_file(html_path, title="Risky")

    client.post_multipart.assert_not_called()
    client.post_json.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_draft_service_digest_ssot_omits_pre_code_terms(tmp_path: Path) -> None:
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n")
    html_path = tmp_path / "digest-ssot.wechat.html"
    html_path.write_text(
        "<html><body><p>正常教程正文足够长通过合规扫描与摘要提取。</p>"
        "<pre><code>保本理财，稳赚不赔</code></pre>"
        '<img src="cover.png" alt="cover"></body></html>',
        encoding="utf-8",
    )
    client = AsyncMock(spec=WeChatOfficialApiClient)
    client.post_multipart = AsyncMock(
        side_effect=[
            {"url": "https://mmbiz.qpic.cn/content-img"},
            {"media_id": "thumb_media_integration"},
        ]
    )
    client.post_json = AsyncMock(return_value={"media_id": "draft_media_integration"})

    service = WeChatDraftService(client)
    result = await service.create_draft_from_html_file(html_path, title="Digest SSOT")

    assert result.media_id == "draft_media_integration"
    draft_payload = client.post_json.await_args.args[1]
    digest = str(draft_payload["articles"][0]["digest"])
    assert "保本" not in digest
    assert "正常教程" in digest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_draft_service_returns_real_compliance_warnings_on_success(tmp_path: Path) -> None:
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n")
    html_path = tmp_path / "warning.wechat.html"
    html_path.write_text(
        '<html><body><p>这款茶能排毒养颜，正文足够长。</p><img src="cover.png" alt="cover"></body></html>',
        encoding="utf-8",
    )
    client = AsyncMock(spec=WeChatOfficialApiClient)
    client.post_multipart = AsyncMock(
        side_effect=[
            {"url": "https://mmbiz.qpic.cn/content-img"},
            {"media_id": "thumb_media_warn"},
        ]
    )
    client.post_json = AsyncMock(return_value={"media_id": "draft_media_warn"})

    service = WeChatDraftService(client)
    result = await service.create_draft_from_html_file(html_path, title="Wellness Tips")

    assert result.media_id == "draft_media_warn"
    assert len(result.compliance_warnings) == 1
    assert result.compliance_warnings[0]["category"] == "medical_efficacy"
    assert result.compliance_warnings[0]["highRisk"] is False
