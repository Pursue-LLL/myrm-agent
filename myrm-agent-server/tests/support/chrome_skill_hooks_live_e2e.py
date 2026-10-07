"""Chrome LIVE E2E support: a user-installed skill with command hooks, set up through the product's own API.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: private SHPOIB backend + CDP page helpers)
- cdp_chat.support (POS: live provider readiness, private backend log offset, private-API HITL pin)

[OUTPUT]
- setup_skill_chat(): providers + agent owning the adopted hook skill + empty chat
- SkillChat: one probe (agent, chat, the folder hooks write into)
- audit_hooks() / fail_closed_hooks(): SKILL.md ``hooks:`` blocks that write observable files
- BASH_TOOL / DONE_TOKEN / BLOCKED_TOKEN / COMMAND_OUTPUT: the words the probe turns agree on

[POS]
Shared by tests/e2e/test_skill_hooks_live_chrome_e2e.py; the browser side lives in chrome_skill_hooks_composer and
what a turn left behind is read by chrome_skill_hooks_observe.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import (  # noqa: E402
    _pin_hitl_on_api_with_retry,
    snapshot_backend_log_offset,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    get_e2e_api_url,
    http_json,
    prepare_e2e_ui_session,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger  # noqa: E402
from tests.support.hitl_live_e2e import hitl_probe  # noqa: E402

BASH_TOOL = "bash_code_execute_tool"
DONE_TOKEN = "HOOKS-E2E-DONE"
BLOCKED_TOKEN = "HOOKS-E2E-BLOCKED"
COMMAND_OUTPUT = "HOOK-E2E-OK"

_AGENT_SYSTEM_PROMPT = (
    f"You run shell commands with {BASH_TOOL} when the user asks. "
    "Call it exactly once with the command the user gives, then reply with the exact words the user requests."
)


# --- SKILL.md --------------------------------------------------------------------------------------


def _skill_md(name: str, hooks_yaml: str) -> str:
    return f"""---
name: {name}
description: E2E probe skill whose command hooks audit the agent run into a local folder.
hooks:
{hooks_yaml}---
# {name}

When asked, run the requested shell command with the bash tool.
"""


def audit_hooks(out: Path) -> str:
    """Benign audit hooks plus a third-party ``eval`` hook the command gate must refuse."""
    return f"""  SessionStart:
    - script: 'printf "%s" "$ARGUMENTS" > {out}/session_payload.json'
      description: Capture the session payload.
    - script: 'eval "echo escalated > {out}/escalated.marker"'
      description: Third-party escalation the gate must refuse.
  PreToolUse:
    - script: 'printf "%s" $ARGUMENTS > {out}/pre_tool_payload.json'
      tools: [bash_*]
      description: Capture the bash call before it runs.
  PostToolUse:
    - script: 'printf "%s" $ARGUMENTS > {out}/post_tool_payload.json'
      tools: [bash_*]
      description: Capture the bash call after it ran.
  SessionEnd:
    - script: 'echo ended >> {out}/audit.log'
      description: Mark the end of the session.
"""


def fail_closed_hooks(out: Path) -> str:
    """A PreToolUse hook the gate refuses, declared ``fail_closed``: the refusal must block the tool."""
    return f"""  PreToolUse:
    - script: 'printf "%s" $ARGUMENTS > {out}/pre_tool_payload.json'
      tools: [bash_*]
      description: Capture the bash call before the guard decides.
    - script: 'eval "echo escalated > {out}/escalated.marker"'
      tools: [bash_*]
      failure_mode: fail_closed
      description: Refused by the command gate; fail_closed turns the refusal into a block.
  PostToolUse:
    - script: 'printf "%s" $ARGUMENTS > {out}/post_tool_payload.json'
      tools: [bash_*]
      description: Only reached when the bash call actually ran.
"""


# --- product API setup -----------------------------------------------------------------------------


def _create_agent(api_url: str, suffix: str, *, yolo: bool) -> str:
    """Custom agent with the bash tool; ``yolo`` decides whether approval cards interrupt the turn."""
    overrides: dict[str, object] = {"yoloModeEnabled": True, "yolo_mode_enabled_at": time.time()} if yolo else {}
    created = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": f"Skill Hooks E2E {suffix}",
            "description": "Skill hooks live E2E probe agent",
            "system_prompt": _AGENT_SYSTEM_PROMPT,
            "skill_ids": [],
            "mcp_ids": [],
            "enabled_builtin_tools": ["code_execute"],
            "security_overrides": overrides,
        },
    )
    assert isinstance(created, dict), created
    data = created.get("data")
    agent_id = data.get("id") if isinstance(data, dict) else created.get("id")
    assert isinstance(agent_id, str) and agent_id, created
    return agent_id


def _create_chat(api_url: str, chat_id: str, agent_id: str) -> None:
    created = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "Skill hooks live E2E",
            "agent_id": agent_id,
            "action_mode": "agent",
            "messages": [],
        },
    )
    assert isinstance(created, dict) and created.get("success") is True, created


def _install_skill(api_url: str, skills_dir: Path, agent_id: str, name: str) -> str:
    """Adopt the local skill folder into the agent through the product's own adoption endpoint."""
    preview = http_json(
        "POST",
        f"{api_url}/api/v1/skills/local/paths/preview",
        body={"path": str(skills_dir)},
    )
    assert isinstance(preview, dict), preview
    items = [item for item in preview.get("skills") or [] if isinstance(item, dict)]
    target = next((item for item in items if item.get("name") == name), None)
    assert target is not None, f"skill {name!r} not found in preview: {json.dumps(preview, ensure_ascii=False)[:600]}"
    skill_id = str(target.get("skill_id") or "")
    assert skill_id.startswith("local::"), target
    adopted = http_json(
        "POST",
        f"{api_url}/api/v1/skills/local/paths/adopt",
        body={"path": str(skills_dir), "selected_skill_ids": [skill_id], "agent_id": agent_id},
    )
    assert isinstance(adopted, dict) and skill_id in (adopted.get("adopted_skill_ids") or []), adopted
    # Pick the adopted skill for the agent, as the agent editor does; the slash palette lists an agent's own skills.
    bound = http_json("PUT", f"{api_url}/api/v1/user-agents/{agent_id}", body={"skill_ids": [skill_id]})
    assert isinstance(bound, dict) and bound.get("success") is not False, bound
    return skill_id


def _pin_hitl_on_private_api(api_url: str) -> None:
    """Turn YOLO off on this probe's own backend only; the shared dev backend's config stays untouched."""
    _pin_hitl_on_api_with_retry(api_url)
    probe = hitl_probe(api_url)
    assert not probe.get("yolo") and probe.get("expects_ask") is True, f"HITL not pinned on {api_url}: {probe!r}"


@dataclass(frozen=True)
class SkillChat:
    """One probe: an agent that owns the hook skill, an empty chat for it, and the folder hooks write into."""

    skill_name: str
    agent_id: str
    chat_id: str
    out: Path
    log_offset: int  # size of the private backend's log when the probe was set up

    @property
    def ui_path(self) -> str:
        return f"/{self.chat_id}?agentId={self.agent_id}"


def setup_skill_chat(
    tmp_path: Path,
    ledger: E2EResourceLedger,
    prefix: str,
    hooks_for: Callable[[Path], str],
    *,
    yolo: bool = True,
) -> SkillChat:
    """Providers, an agent owning the adopted hook skill, and an empty chat for it."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")
    if not yolo:
        _pin_hitl_on_private_api(api_url)

    suffix = uuid.uuid4().hex[:8]
    skill_name = f"{prefix}-{suffix}"
    out = tmp_path / "hook-out"
    out.mkdir()
    skills_dir = tmp_path / "skills"
    (skills_dir / skill_name).mkdir(parents=True)
    (skills_dir / skill_name / "SKILL.md").write_text(_skill_md(skill_name, hooks_for(out)), encoding="utf-8")

    agent_id = _create_agent(api_url, suffix, yolo=yolo)
    ledger.register("agent", agent_id)
    _install_skill(api_url, skills_dir, agent_id, skill_name)

    chat_id = f"e2ehooks{suffix}"
    _create_chat(api_url, chat_id, agent_id)
    ledger.register("chat", chat_id)
    return SkillChat(
        skill_name=skill_name,
        agent_id=agent_id,
        chat_id=chat_id,
        out=out,
        log_offset=snapshot_backend_log_offset(api_url),
    )
