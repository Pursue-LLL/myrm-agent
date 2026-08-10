"""WeChat Official Account draft + credential endpoints.

[INPUT]
- draft_service::WeChatDraftService (POS: draft publishing)
- wechat_api_client::WeChatOfficialApiClient (POS: token client)
- ConfigService (credential loading)

[OUTPUT]
- POST /wechat-official/test: credential connectivity test
- GET /wechat-official/egress-ip: sandbox public egress IP for Official Account whitelist setup
- POST /wechat-official/draft: HITL draft publish from HTML artifact (path validation before credentials)

[POS]
HITL-only WeChat draft API. Frontend artifact card calls draft endpoint after user confirmation.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.channels.schemas import ChannelTestResponse, WeChatOfficialTestRequest
from app.channels.core.exceptions import ChannelConnectionError
from app.config.deploy_mode import is_local_mode

router = APIRouter()
logger = logging.getLogger(__name__)


class WeChatDraftRequest(BaseModel):
    html_path: str = Field(..., alias="htmlPath", min_length=1, max_length=4096)
    title: str = Field(..., min_length=1, max_length=64)
    author: str = Field(default="", max_length=8)
    digest: str = Field(default="", max_length=120)
    cover_path: str | None = Field(default=None, alias="coverPath", max_length=4096)

    class Config:
        populate_by_name = True


class WeChatEgressIpResponse(BaseModel):
    egress_ip: str = Field(..., alias="egressIp")

    class Config:
        populate_by_name = True


class WeChatDraftResponse(BaseModel):
    media_id: str = Field(..., alias="mediaId")
    uploaded_image_count: int = Field(..., alias="uploadedImageCount")
    manage_url: str = Field(..., alias="manageUrl")
    compliance_warnings: list[dict[str, object]] = Field(default_factory=list, alias="complianceWarnings")

    class Config:
        populate_by_name = True


@router.get("/wechat-official/egress-ip", response_model=WeChatEgressIpResponse)
async def wechat_official_egress_ip() -> WeChatEgressIpResponse:
    from app.channels.providers.wechat.egress_ip import resolve_public_egress_ip

    try:
        egress_ip = await resolve_public_egress_ip()
    except Exception as exc:
        logger.warning("WeChat egress IP probe failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Unable to resolve server egress IP. Try again later or check outbound network access.",
        ) from exc
    return WeChatEgressIpResponse(egressIp=egress_ip)


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
async def push_wechat_official_draft(body: WeChatDraftRequest, request: Request) -> WeChatDraftResponse:
    html_path = _resolve_allowed_path(body.html_path)
    cover_path = _resolve_allowed_path(body.cover_path) if body.cover_path else None

    if not body.author.strip():
        raise HTTPException(
            status_code=400,
            detail="Author is required (max 8 characters).",
        )

    locale = _resolve_request_locale(request.headers.get("accept-language"))

    creds = await _load_official_credentials()
    if creds is None:
        raise HTTPException(
            status_code=400,
            detail="WeChat Official Account credentials not configured. Add AppID and AppSecret in Settings.",
        )

    from app.channels.providers.wechat.draft_service import WeChatDraftService
    from app.channels.providers.wechat.wechat_api_client import WeChatOfficialApiClient

    client = WeChatOfficialApiClient(
        str(creds["appId"]),
        str(creds["appSecret"]),
        locale=locale,
    )
    try:
        service = WeChatDraftService(client)
        result = await service.create_draft_from_html_file(
            html_path,
            title=body.title,
            author=body.author,
            digest=body.digest,
            cover_path=cover_path,
            locale=locale,
        )
    except FileNotFoundError as exc:
        logger.warning("WeChat draft publish cover not found: %s", exc)
        raise HTTPException(status_code=404, detail="Cover file not found") from exc
    except ValueError as exc:
        from app.services.compliance.wechat_compliance_scan import (
            WeChatComplianceBlockedError,
            compliance_hits_payload,
        )

        if isinstance(exc, WeChatComplianceBlockedError):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "wechat_compliance_blocked",
                    "message": str(exc),
                    "hits": compliance_hits_payload(exc.result, locale=exc.locale),
                },
            ) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ChannelConnectionError as exc:
        logger.error("WeChat draft publish failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("WeChat draft publish failed: %s", exc)
        raise HTTPException(status_code=502, detail="WeChat API call failed") from exc
    finally:
        await client.close()

    return WeChatDraftResponse(
        mediaId=result.media_id,
        uploadedImageCount=result.uploaded_image_count,
        manageUrl="https://mp.weixin.qq.com/",
        complianceWarnings=list(result.compliance_warnings),
    )


async def _load_official_credentials() -> dict[str, object] | None:
    from app.services.config.service import ConfigService

    service = ConfigService()
    try:
        record = await service.get("wechatOfficialCredentials")
    except Exception:
        return None
    if record is None:
        return None
    raw = record.value
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

    allowed_roots = _collect_allowed_workspace_roots()
    if not allowed_roots:
        raise HTTPException(
            status_code=503,
            detail="Workspace root unavailable; cannot validate file paths for draft publish.",
        )

    if not any(_path_is_under_root(resolved, root) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Access denied: path outside workspace")

    return resolved


def _path_is_under_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _collect_allowed_workspace_roots() -> list[Path]:
    roots: list[Path] = []
    primary = _get_workspace_root()
    if primary:
        roots.append(Path(primary).resolve())
    if is_local_mode():
        harness_workspaces = Path.home() / ".myrm" / "harness" / "workspaces"
        if harness_workspaces.is_dir():
            harness_resolved = harness_workspaces.resolve()
            if harness_resolved not in roots:
                roots.append(harness_resolved)
    return roots


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


def _resolve_request_locale(accept_language: str | None) -> str:
    if not accept_language:
        return "zh"
    first = accept_language.split(",")[0].strip().lower()
    if first.startswith("zh"):
        return "zh"
    return "en"
