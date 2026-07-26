"""Integration: foreground bash spill → UECD evicted file (no LLM)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import (
    create_bash_code_execute_tool,
)
from myrm_agent_harness.core.context_vars import chat_id_var, workspace_root_var
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import set_executor
from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import (
    bind_workspace_storage_root,
)

_MARKER = "UECD_BASH_FG_INTEGRATION_MARKER"
_SPILL_COMMAND = f"echo {_MARKER} && seq 1 25000"


def _make_local_executor(workspace: Path) -> object:
    from myrm_agent_harness.toolkits.code_execution.executors.local.executor import (
        LocalExecutor,
    )
    from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import (
        NullProvider,
    )
    from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import (
        SandboxStatus,
    )

    executor = LocalExecutor(ExecutionConfig())
    executor.bind_workspace(str(workspace))
    null_result = (
        NullProvider(),
        SandboxStatus(enabled=False, provider_name="null", reason="test"),
    )
    patch(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detector.detect_sandbox_provider",
        return_value=null_result,
    ).start()
    patch(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider",
        return_value=null_result,
    ).start()
    return executor


@pytest.fixture(autouse=True)
def _stop_sandbox_patches() -> None:
    yield
    import unittest.mock

    unittest.mock.patch.stopall()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_foreground_bash_spill_persists_evicted_output(tmp_path: Path) -> None:
    """Direct bash tool invoke must spill large stdout to .context/{chat_id}/evicted/."""
    executor = _make_local_executor(tmp_path)
    set_executor(executor)
    bind_workspace_storage_root(tmp_path)

    raw_chat_id = "e2ebashfg-integration"
    session_id = f"chat_{raw_chat_id}"
    w_tok = workspace_root_var.set(str(tmp_path))
    c_tok = chat_id_var.set(raw_chat_id)
    config: dict[str, object] = {
        "configurable": {
            "context": {
                "session_id": session_id,
                "chat_id": raw_chat_id,
                "workspace_path": str(tmp_path),
                "workspaces_storage_root": str(tmp_path),
            }
        }
    }

    bash_tool = create_bash_code_execute_tool()
    events: list[tuple[str, object]] = []

    async def _capture(event_name: str, payload: object, **_: object) -> None:
        events.append((event_name, payload))

    try:
        with (
            patch(
                "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
                side_effect=_capture,
            ),
            patch(
                "myrm_agent_harness.agent.skills.mcp.notify_registry.session_scope",
                return_value=AsyncMock(
                    __aenter__=AsyncMock(return_value=None),
                    __aexit__=AsyncMock(return_value=False),
                ),
            ),
        ):
            result = await bash_tool.ainvoke(
                {
                    "command": _SPILL_COMMAND,
                    "reason": "integration foreground spill",
                    "run_in_background": False,
                    "timeout": 90,
                },
                config=config,
            )

        content = str(result.get("content") or "")
        assert "LARGE OUTPUT TRUNCATED" in content, content[:400]
        evicted_events = [
            p for name, p in events if name == "tool_evicted_ref"
        ]
        assert evicted_events, f"expected tool_evicted_ref event, got {events!r}"
        ref_payload = evicted_events[0]
        assert isinstance(ref_payload, dict)
        evicted_ref = str(ref_payload.get("evicted_ref") or "")
        assert evicted_ref.startswith("output_"), evicted_ref

        spill_path = (
            tmp_path / ".context" / raw_chat_id / "evicted" / evicted_ref
        )
        assert spill_path.is_file(), spill_path
        spill_text = spill_path.read_text(encoding="utf-8")
        assert _MARKER in spill_text
        assert len(spill_text) > 50_000
    finally:
        workspace_root_var.reset(w_tok)
        chat_id_var.reset(c_tok)
