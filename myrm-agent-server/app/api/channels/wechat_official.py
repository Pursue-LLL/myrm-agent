"""WeChat Official Account draft + credential endpoints.

[INPUT]
- draft_service::WeChatDraftService (POS: draft publishing)
- wechat_api_client::WeChatOfficialApiClient (POS: token client)
- ConfigService (credential loading)

[OUTPUT]
- POST /wechat-official/test: credential connectivity test
- POST /wechat-official/draft: HITL draft publish from HTML artifact (path validation before credentials)

[POS]
HITL-only WeChat draft API. Frontend artifact card calls draft endpoint after user confirmation.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.channels.schemas import ChannelTestResponse, WeChatOfficialTestRequest
from app.config.deploy_mode import is_local_mode

router = APIRouter()
logger = logging.getLogger(__name__)


class WeChatDraftRequest(BaseModel):
    html_path: str = Field(..., alias="htmlPath", min_length=1, max_length=4096)
    title: str = Field(..., min_length=1, max_length=64)
    author: str = Field(default="", max_length=32)
    digest: str = Field(default="", max_length=120)
    cover_path: str | None = Field(default=None, alias="coverPath", max_length=4096)

    class Config:
        populate_by_name = True


class WeChatDraftResponse(BaseModel):
    media_id: str = Field(..., alias="mediaId")
    uploaded_image_count: int = Field(..., alias="uploadedImageCount")
    manage_url: str = Field(..., alias="manageUrl")

    class Config:
        populate_by_name = True


@router.post("/wechat-official/test", response_model=ChannelTestResponse)
async def wechat_official_test_connection(
    body: WeChatOfficialTestRequest,
) -> ChannelTestResponse:
    from app.channels.providers.wechat.wechat_api_client import WeChatOfficialApiClient

    client = WeChatOfficialApiClient(body.app_id, body.app_secret)
    try:
        await client.ensure_token()
        return ChannelTestResponse(ok=True, message="Connection successful")
    except Exception as exc:
        return ChannelTestResponse(ok=False, message=str(exc))
    finally:
        await client.close()


@router.post("/wechat-official/draft", response_model=WeChatDraftResponse)
async def push_wechat_official_draft(body: WeChatDraftRequest) -> WeChatDraftResponse:
    html_path = _resolve_allowed_path(body.html_path)
    cover_path = _resolve_allowed_path(body.cover_path) if body.cover_path else None

    creds = await _load_official_credentials()
    if creds is None:
        raise HTTPException(
            status_code=400,
            detail="WeChat Official Account credentials not configured. Add AppID and AppSecret in Settings.",
        )

    from app.channels.providers.wechat.draft_service import WeChatDraftService
    from app.channels.providers.wechat.wechat_api_client import WeChatOfficialApiClient

    client = WeChatOfficialApiClient(str(creds["appId"]), str(creds["appSecret"]))
    try:
        service = WeChatDraftService(client)
        result = await service.create_draft_from_html_file(
            html_path,
            title=body.title,
            author=body.author,
            digest=body.digest,
            cover_path=cover_path,
        )
    except FileNotFoundError as exc:
        logger.warning("WeChat draft publish cover not found: %s", exc)
        raise HTTPException(status_code=404, detail="Cover file not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("WeChat draft publish failed: %s", exc)
        raise HTTPException(status_code=502, detail="WeChat API call failed") from exc
    finally:
        await client.close()

    return WeChatDraftResponse(
        mediaId=result.media_id,
        uploadedImageCount=result.uploaded_image_count,
        manageUrl="https://mp.weixin.qq.com/",
    )


async def _load_official_credentials() -> dict[str, object] | None:
    from app.services.config.service import ConfigService

    service = ConfigService()
    try:
        raw = await service.get("wechatOfficialCredentials")
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    app_id = raw.get("appId")
    app_secret = raw.get("appSecret")
    if not app_id or not app_secret:
        return None
    return raw


def _resolve_allowed_path(raw_path: str) -> Path:
    expanded = os.path.expanduser(raw_path.strip())
    resolved = Path(expanded).resolve()
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {raw_path}")

    workspace_root = _get_workspace_root()
    if not workspace_root:
        raise HTTPException(
            status_code=503,
            detail="Workspace root unavailable; cannot validate file paths for draft publish.",
        )

    root = Path(workspace_root).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied: path outside workspace") from exc

    return resolved


def _get_workspace_root() -> str | None:
    workspace = os.environ.get("MYRM_WORKSPACE_ROOT")
    if workspace and os.path.isdir(workspace):
        return workspace

    try:
        from myrm_agent_harness.toolkits.code_execution.workspace.registry import (
            get_active_workspace_path,
        )

        active = get_active_workspace_path()
        if active and os.path.isdir(active):
            return active
    except Exception:
        pass

    if is_local_mode():
        default_workspace = os.path.join(os.path.expanduser("~"), ".myrm", "workspace")
        if os.path.isdir(default_workspace):
            return default_workspace

    return None
