"""Local-only WeChat Official draft Chrome E2E seed routes.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: gate local-only access)
- app.services.agent.agent_service::AgentService (POS: resolve default agent)
- app.services.chat.chat_service::ChatService (POS: seed chat + messages)
- app.services.config.service::ConfigService (POS: WeChat draft settings)

[OUTPUT]
- router: POST /test/seed-wechat-official-settings-fixture (POS: E2E seed endpoint)

[POS]
app.api.chats.test_fixtures 子包。WeChat Official draft Chrome E2E 的 local-only seed
端点（is_local_mode 守卫，仅 local dev 暴露）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService
from app.services.config.service import ConfigService

router = APIRouter()

_COVER_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"

_VARIANT_HTML: dict[str, str] = {
    "compliance_block": (
        "<html><body><p>集赞 20 个送礼品，分享到朋友圈解锁全文。</p>"
        '<img src="cover.png" alt="cover"></body></html>'
    ),
    "digest_ssot": (
        "<html><body><p>正常教程正文足够长通过合规扫描与摘要提取。</p>"
        "<pre><code>保本理财，稳赚不赔</code></pre>"
        '<img src="cover.png" alt="cover"></body></html>'
    ),
}


@router.post("/test/seed-wechat-official-settings-fixture", include_in_schema=False)
async def seed_wechat_official_settings_fixture() -> dict[str, str]:
    """Seed WeChat Official credentials for Settings Chrome E2E (namespace-safe)."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    config = ConfigService()
    await config.set(
        "wechatOfficialCredentials",
        {
            "appId": "wx_e2e_settings",
            "appSecret": "e2e_settings_secret",
            "token": "",
            "encodingAesKey": "",
        },
        device_id="wechat-settings-e2e-seed",
    )

    return {"ok": "true"}


@router.post("/test/seed-wechat-draft-fixture", include_in_schema=False)
async def seed_wechat_draft_fixture(variant: str = "compliance_block") -> dict[str, str]:
    """Seed html artifact + optional WeChat credentials for Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    normalized = variant.strip().lower()
    html_body = _VARIANT_HTML.get(normalized)
    if html_body is None:
        raise HTTPException(status_code=400, detail=f"Unsupported wechat-draft variant: {variant}")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(status_code=500, detail="No agents available for WeChat draft E2E seed")

    agent = agents[0]
    chat_id = f"e2ewxd{uuid4().hex[:8]}"
    file_id = f"wxdraft-{uuid4().hex[:8]}"
    filename = "article.wechat.html"

    from app.services.agent.params.workspace_resolve import resolve_default_chat_workspace_dir

    workspace_dir = await resolve_default_chat_workspace_dir(chat_id, persist_workspace=True)
    if not workspace_dir:
        raise HTTPException(status_code=500, detail="Failed to resolve workspace for WeChat draft E2E seed")

    workspace = Path(workspace_dir)
    cover_path = workspace / "cover.png"
    cover_path.write_bytes(_COVER_BYTES)
    html_path = workspace / filename
    html_path.write_text(html_body, encoding="utf-8")

    config = ConfigService()
    await config.set(
        "wechatOfficialCredentials",
        {"appId": "wx_e2e_fixture", "appSecret": "e2e_fixture_secret"},
        device_id="wechat-draft-e2e-seed",
    )

    artifact: dict[str, object] = {
        "id": file_id,
        "filename": filename,
        "type": "html",
        "content_type": "text/html",
        "size": html_path.stat().st_size,
        "preview_url": f"/api/v1/files/artifacts/{file_id}/preview",
        "download_url": f"/api/v1/files/artifacts/{file_id}/download",
        "file_path": str(html_path.resolve()),
    }

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="WeChat draft Chrome E2E",
            agent_id=agent.id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    await ChatService.append_message(chat_id, "user", "WeChat draft E2E fixture question", now, timezone)
    await ChatService.append_message(
        chat_id,
        "assistant",
        "WeChat draft E2E fixture answer with html artifact.",
        now,
        timezone,
        extra_data={"artifacts": [artifact]},
    )

    return {
        "chat_id": chat_id,
        "agent_id": agent.id,
        "html_path": str(html_path.resolve()),
        "cover_path": str(cover_path.resolve()),
        "ui_path": f"/{chat_id}",
        "variant": normalized,
    }
