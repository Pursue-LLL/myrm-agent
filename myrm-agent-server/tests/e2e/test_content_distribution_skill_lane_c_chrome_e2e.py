"""Chrome LIVE Lane-C E2E: content-distribution-pipeline skill governs a real chat turn.

The skill's Postiz draft-sync section applies only when Postiz MCP tools are
connected. This probe runs the turn with no Postiz connected and asserts the
executable half of that contract against a real model and the real UI:

1. The prebuilt skill is enabled, bound to a fresh agent, slash-invoked from
   the composer, and the turn completes with per-platform variants (the user
   prompt asks for inline delivery, which overrides the skill's file-bundle
   default).
2. The reply must not fabricate a Postiz execution (no preview links, no
   "already synced / draft created" claims) while Postiz is absent.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import snapshot_backend_log_offset, wait_e2e_provider_ready  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    prepare_e2e_ui_session,
    wait_for_state,
)
from tests.support.chrome_skill_hooks_composer import drive_chat_turn  # noqa: E402
from tests.support.chrome_skill_hooks_live_e2e import SkillChat  # noqa: E402
from tests.support.chrome_skill_hooks_observe import (  # noqa: E402
    transcript_text,
    wait_completed_assistant_reply_containing,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger  # noqa: E402

_SKILL_ID = "content-distribution-pipeline"

_PROMPT = (
    "请把下面这段产品介绍，改写成适合在 X、LinkedIn、小红书三个平台分别发布的帖子，"
    "每个平台一版，体现各平台的表达风格。请直接在回复正文中给出三个平台的完整文案，不要只保存为文件：\n\n"
    "「Myrm 是一款开源的个人 AI 助手，能在本地电脑或云端沙箱中运行，帮用户处理文档、写代码和完成日常办公任务，数据始终由用户自己掌控。」"
)

# Claims that would mean the model fabricated a Postiz execution without tools.
_FABRICATION_MARKERS = (
    "已同步到 Postiz",
    "已创建 Postiz 草稿",
    "Postiz 草稿已创建",
    "已排期到 Postiz",
    "已发布到 Postiz",
    "postiz.com",
)

_AGENT_BOUND_JS = """((agentId) => {
  const bound = window.__myrmChatStore?.getState?.()?.agentConfig?.agentId ?? null;
  return { ready: bound === agentId, bound };
})"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_content_distribution_skill_live_turn_without_postiz(tmp_path: Path, e2e_resource_ledger: E2EResourceLedger) -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    enabled = http_json("POST", f"{api_url}/api/v1/skills/{_SKILL_ID}/enable")
    assert isinstance(enabled, dict), enabled
    enable_body = enabled.get("data") if isinstance(enabled.get("data"), dict) else enabled
    assert enable_body.get("enabled") is True, enabled

    suffix = uuid.uuid4().hex[:8]
    created = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": f"Content Distribution Lane-C E2E {suffix}",
            "description": "Lane-C probe for the content-distribution-pipeline prebuilt skill",
            "system_prompt": "You are a helpful personal assistant.",
            "skill_ids": [_SKILL_ID],
            "mcp_ids": [],
            "enabled_builtin_tools": [],
        },
    )
    assert isinstance(created, dict), created
    created_data = created.get("data")
    agent_id = created_data.get("id") if isinstance(created_data, dict) else created.get("id")
    assert isinstance(agent_id, str) and agent_id, created
    e2e_resource_ledger.register("agent", agent_id)

    bound = http_json("GET", f"{api_url}/api/v1/user-agents/{agent_id}")
    bound_data = bound.get("data") if isinstance(bound, dict) else None
    bound_ids = bound_data.get("skill_ids") if isinstance(bound_data, dict) else None
    assert isinstance(bound_ids, list) and _SKILL_ID in bound_ids, bound

    chat_id = f"e2econtent{suffix}"
    created_chat = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "Content distribution Lane-C E2E",
            "agent_id": agent_id,
            "action_mode": "agent",
            "messages": [],
        },
    )
    assert isinstance(created_chat, dict) and created_chat.get("success") is True, created_chat
    e2e_resource_ledger.register("chat", chat_id)

    probe = SkillChat(
        skill_name=_SKILL_ID,
        agent_id=agent_id,
        chat_id=chat_id,
        out=tmp_path,
        log_offset=snapshot_backend_log_offset(api_url),
    )
    chat_url = f"{ui_url.rstrip('/')}{probe.ui_path}"

    def agent_bound(client: ChromeMcpClient, page: McpPage) -> None:
        applied = wait_for_state(
            client,
            page,
            f"({_AGENT_BOUND_JS})({json.dumps(agent_id)})",
            timeout_sec=90.0,
            page_url=chat_url,
        )
        assert applied.get("ready") is True, applied

    drive_chat_turn(ui_url, probe, _PROMPT, before_send=agent_bound)

    reply = wait_completed_assistant_reply_containing(chat_id, api_url, "小红书", timeout_sec=300.0)
    print(f"E2E_ASSISTANT_REPLY[{chat_id}]: {reply[:500]}", flush=True)
    assert ("LinkedIn" in reply) or ("领英" in reply), reply[:800]
    assert any(marker in reply for marker in ("Twitter", "推特", "X 平台", "X平台", "X：", "X:")), reply[:800]

    transcript = transcript_text(chat_id, api_url)
    for marker in _FABRICATION_MARKERS:
        assert marker not in transcript, f"fabricated Postiz execution claim: {marker}"
