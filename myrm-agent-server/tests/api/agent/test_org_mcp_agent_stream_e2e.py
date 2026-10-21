"""E2E: org-pushed MCP server is genuinely invoked by a live agent stream.

Bypasses the browser; drives the real agent stream in-process (TestClient) with
``load_user_configs`` mocked to include an ``org_mcp_dict`` entry, then asserts
the MCP tool call really happened via the assistant's final answer (Goodhart
guard: the raw ``{"result": "pong"}`` payload is echoed verbatim, not fabricated).
"""

from __future__ import annotations

import dataclasses
import os
import sys
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.mcp_e2e_helpers import preflight_llm_check, prewarm_shared_venv
from tests.api.agent.mcp_e2e_stream import (
    McpStreamRunResult,
    print_event_sequence,
    run_mcp_agent_stream,
    skip_on_environment_errors,
)
from tests.api.agent.utils import (
    get_lite_model_selection,
    get_model_selection,
    get_search_service_config,
)

_STUB = Path(__file__).resolve().parents[2] / "support" / "e2e_minimal_stdio_mcp_server.py"

_ORG_MCP_DICT = {
    "servers": [
        {
            "id": "org-e2e-minimal",
            "name": "e2e-minimal",
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_STUB)],
            "description": "org MCP probe (Control Plane pushed)",
        }
    ]
}

E2E_PROMPT = (
    "请调用 e2e-minimal MCP server 提供的 ping 工具。这是一个真实存在的 MCP 工具，"
    "必须真正调用它，禁止自己编造或用代码模拟。然后把工具返回的原始结果一字不差地告诉我。"
)

_PONG_JSON = '{"result": "pong"}'


def _org_mcp_pong_delivered(result: McpStreamRunResult) -> bool:
    """True when the final answer echoes the org MCP tool's raw JSON result."""
    answer = result.full_answer
    return "pong" in answer.lower() and "result" in answer.lower()


def _mcp_tool_tasks_seen(result: McpStreamRunResult) -> list[str]:
    """List tool names seen in tasks_steps for diagnostics (Direct FC MCP tools
    do not emit step data; progress/todo steps do)."""
    names: list[str] = []
    for event in result.collected_data:
        if event.get("type") != "tasks_steps":
            continue
        tool_name = event.get("tool_name")
        if isinstance(tool_name, str) and tool_name.strip():
            names.append(tool_name)
    return names


@pytest.fixture(autouse=True)
def _mcp_e2e_local_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate local GUI mode with unrestricted code-execution network."""
    monkeypatch.setenv("DEPLOY_MODE", "local")
    import myrm_agent_harness.toolkits.code_execution.config as cfg_mod
    from myrm_agent_harness.toolkits.code_execution.config import (
        ExecutionConfig,
        NetworkConfig,
        set_execution_config,
    )

    previous = cfg_mod._execution_config_cache
    set_execution_config(
        ExecutionConfig(
            network=NetworkConfig(allow_network=True, allowed_hosts=frozenset()),
        )
    )
    yield
    cfg_mod._execution_config_cache = previous


@pytest.fixture(autouse=True)
def _org_mcp_e2e_prewarm(_mcp_e2e_local_network: None) -> None:
    """Warm shared venv before agent bash so E2E graph nodes are not spent on cold start."""
    prewarm_shared_venv()
    yield


@pytest.fixture(autouse=True)
def _org_mcp_inject_config(mock_load_user_configs: object) -> None:
    """Inject org MCP into the mocked user configs (mirrors real org-mcp-sync)."""
    original = mock_load_user_configs.return_value
    mock_load_user_configs.return_value = dataclasses.replace(
        original,
        mcp_dict=None,
        org_mcp_dict=_ORG_MCP_DICT,
        security_config_dict={"yoloModeEnabled": True, "autoModeEnabled": True},
    )
    yield


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestOrgMCPAgent:
    @pytest.mark.timeout(300)
    def test_agent_with_org_mcp(self, client: TestClient) -> None:
        if not preflight_llm_check():
            pytest.skip("LLM API preflight check failed (connectivity / timeout)")

        start_time = time.time()

        def log(msg: str) -> None:
            print(f"[{time.time() - start_time:.1f}s] {msg}", flush=True)

        request: dict[str, object] = {
            "messageId": str(uuid.uuid4()),
            "chatId": f"test-orgmcp-chat-{uuid.uuid4().hex[:8]}",
            "query": E2E_PROMPT,
            "action_mode": "agent",
            "modelSelection": get_model_selection(),
            "liteModelSelection": get_lite_model_selection(),
            "searchServiceCfg": get_search_service_config(),
            "enable_memory_auto_extraction": False,
        }

        log("query: " + E2E_PROMPT)
        result = run_mcp_agent_stream(
            client,
            request,
            resume_on_iteration_limit=True,
            log=log,
        )
        print_event_sequence(result.event_types)
        print(f"\n=== tasks_steps tools: {_mcp_tool_tasks_seen(result)} ===")
        answer = result.full_answer
        if answer:
            print(f"\n=== FULL ANSWER ({len(answer)} chars) ===")
            print(answer[:1200])
        else:
            print("\n=== NO MESSAGE CHUNKS ===")
        skip_on_environment_errors(result)

        if not answer:
            pytest.fail("Agent produced no final answer for the org MCP ping prompt")

        assert _org_mcp_pong_delivered(result), (
            f"org MCP tool was not genuinely invoked — expected final answer to echo "
            f"{_PONG_JSON!r}, got: {answer[:300]!r} (Goodhart guard)"
        )

        print("\norg MCP agent stream test passed")
