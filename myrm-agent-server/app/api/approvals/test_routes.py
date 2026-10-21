"""[INPUT]
- app.services.approvals.registry::ApprovalRegistry
- app.services.chat.chat_service::ChatService
- app.config.deploy_mode::is_local_mode

[OUTPUT]
- POST /approvals/test/*: 测试与调试辅助端点（仅 local dev/test 模式可用）

[POS]
提供自动化与端到端测试所需的 Mock 审批注入与清理路由，从主审批路由中解耦以优化单一职责。
"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.approvals.registry import ApprovalRegistry
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["approvals-test"])


@router.post("/test/seed-mock", include_in_schema=False)
async def seed_test_mock_push_approval() -> dict[str, str]:
    """Local dev/test only: seed a chat + inline pending approval for push deeplink E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    chat_id = f"e2epush{uuid4().hex[:8]}"
    await ChatService.create_or_update_chat(
        ChatCreate(chat_id=chat_id, title="Push deeplink E2E", messages=[]),
    )
    record = await ApprovalRegistry.create_approval(
        agent_id="e2e-push-deeplink",
        action_type="delete_file",
        payload={"path": "/tmp/e2e-push-deeplink"},
        reason="Chrome E2E push approval deeplink",
        chat_id=chat_id,
        thread_id=f"e2e-thread-{uuid4().hex[:8]}",
    )
    push_url = f"/{chat_id}?approval={record.id}"
    return {
        "chat_id": chat_id,
        "approval_id": record.id,
        "push_url": push_url,
        "ui_url": push_url,
    }


@router.post("/test/seed-hardened-mock", include_in_schema=False)
async def seed_test_hardened_mock_approval(
    variant: str = "socially_irreversible",
) -> dict[str, str]:
    """Local dev/test only: seed an approval with autoModeSuspended or sociallyIrreversible reviewConfigs."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    chat_id = f"e2ehardened{uuid4().hex[:8]}"
    await ChatService.create_or_update_chat(
        ChatCreate(chat_id=chat_id, title=f"Hardened AutoMode E2E {variant}", messages=[]),
    )

    if variant == "auto_mode_suspended":
        payload: dict[str, object] = {
            "tool_calls": [{"name": "shell_exec", "args": {"command": "cat /tmp/secret"}}],
            "reviewConfigs": [
                {
                    "autoModeSuspended": "consecutive",
                    "hideAllowAlways": True,
                    "smartDenied": True,
                }
            ],
        }
        reason = "Auto mode suspended after 3 consecutive denials"
    else:
        payload = {
            "tool_calls": [{"name": "shell_exec", "args": {"command": "git push origin main"}}],
            "reviewConfigs": [
                {
                    "sociallyIrreversible": True,
                    "hideAllowAlways": True,
                }
            ],
        }
        reason = "Socially irreversible action requires explicit approval"

    record = await ApprovalRegistry.create_approval(
        agent_id="e2e-hardened-automode",
        action_type="subagent_approval",
        payload=payload,
        reason=reason,
        chat_id=chat_id,
        thread_id=f"e2e-thread-{uuid4().hex[:8]}",
    )
    push_url = f"/{chat_id}?approval={record.id}"
    return {
        "chat_id": chat_id,
        "approval_id": record.id,
        "push_url": push_url,
        "ui_url": push_url,
    }


@router.post("/test/cleanup-hardened-mock", include_in_schema=False)
async def cleanup_test_hardened_mock_approval(
    approval_id: str | None = None,
) -> dict[str, object]:
    """Local dev/test only: clean up e2ehardened mock approvals under READ access scope."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    cleaned_ids: list[str] = []
    if approval_id:
        record = await ApprovalRegistry.get_approval(approval_id)
        if record and (str(record.chat_id or "").startswith("e2ehardened") or record.agent_id == "e2e-hardened-automode"):
            await ApprovalRegistry.resolve_approval(approval_id, "reject")
            cleaned_ids.append(approval_id)
    else:
        approvals = await ApprovalRegistry.list_approvals(limit=100)
        for item in approvals:
            if str(item.chat_id or "").startswith("e2ehardened") or item.agent_id == "e2e-hardened-automode":
                await ApprovalRegistry.resolve_approval(item.id, "reject")
                cleaned_ids.append(item.id)

    return {"ok": True, "cleaned_count": len(cleaned_ids), "cleaned_ids": cleaned_ids}
