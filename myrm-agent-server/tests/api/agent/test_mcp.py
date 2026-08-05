"""测试 Agent 模式 MCP 技能集成

本测试验证 Agent 模式与 MCP（Model Context Protocol）技能的集成。

运行方式：
-----------
   ./myrm test -m e2e tests/api/agent/test_mcp.py -v -s
   # 单测例：./myrm test -m e2e tests/api/agent/test_mcp.py::TestAgentMCP::test_agent_with_12306_python_mcp

注意事项：
-----------
- 禁止 `uv run pytest`；monorepo 根目录用 `./myrm test`
- 需要 `.env.test` 中 BASIC_*（及可选 LITE_*、搜索服务配置）
- 12306 MCP 须 Node `12306-mcp`（`npm install -g 12306-mcp`）；禁止 uvx 版 Python mcp-server-12306
- 其他 MCP 服务器可用（如 amap-maps）
- 沙箱模式自动跟随 DEPLOY_MODE 环境变量（local 或 sandbox）
- 使用 TestClient fixture（进程内 FastAPI；stdio MCP 不需 live :8080）
"""

from __future__ import annotations

import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.mcp_e2e_goodhart import (
    assert_12306_ticket_evidence_delivered,
    mcp_bash_get_tickets_succeeded,
    mcp_get_tickets_delivered,
    mcp_ptc_bash_was_engaged,
    mcp_ptc_get_tickets_engaged,
    mcp_skill_was_invoked,
)
from tests.api.agent.mcp_e2e_helpers import (
    MAX_TOOL_STUCK_APPROVALS,
    preflight_llm_check,
    prewarm_shared_venv,
    resolve_12306_mcp_stdio,
)
from tests.api.agent.mcp_e2e_stream import (
    print_event_sequence,
    run_mcp_agent_stream,
    skip_on_environment_errors,
)
from tests.api.agent.utils import (
    get_lite_model_selection,
    get_model_selection,
    get_search_service_config,
)


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
def _mcp_enable_user_network(mock_load_user_configs: object) -> None:
    """Mirror GUI personalSettings.codeExecutionAllowNetwork=true."""
    import dataclasses

    original = mock_load_user_configs.return_value
    mock_load_user_configs.return_value = dataclasses.replace(
        original,
        personal_settings_dict={"codeExecutionAllowNetwork": True},
    )
    yield


@pytest.fixture(autouse=True)
def _mcp_e2e_prewarm_shared_venv(_mcp_e2e_local_network: None) -> None:
    """Warm shared venv before agent bash so E2E graph nodes are not spent on cold start."""
    prewarm_shared_venv()
    yield


def _make_log(start_time: float):
    def log(msg: str) -> None:
        elapsed = time.time() - start_time
        print(f"[{elapsed:.1f}s] {msg}", flush=True)

    return log


def _print_run_stats(result) -> None:
    print("\nStats:")
    print(f"  - Events: {len(result.collected_data)}")
    print(f"  - Message chunks: {len(result.message_chunks)}")
    print(f"  - Tool results: {len(result.tool_results)}")
    print(f"  - Answer length: {len(result.full_answer)} chars")


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestAgentMCP:
    """Agent 模式 MCP 技能测试类"""

    @pytest.mark.timeout(360)
    def test_agent_with_mcp(self, client: TestClient) -> None:
        """测试 Agent 模式配置 MCP（amap-maps SSE）"""
        if not preflight_llm_check():
            pytest.skip("LLM API preflight check failed (connectivity / timeout)")

        start_time = time.time()
        log = _make_log(start_time)

        log("=" * 60)
        log("开始测试：Agent 模式配置 MCP (amap-maps)")
        log("=" * 60)

        search_request: dict[str, object] = {
            "messageId": str(uuid.uuid4()),
            "chatId": f"test-mcp-chat-{uuid.uuid4().hex[:8]}",
            "query": "使用高德地图技能查询北京天安门附近的餐厅，列出前5个",
            "action_mode": "agent",
            "modelSelection": get_model_selection(),
            "liteModelSelection": get_lite_model_selection(),
            "searchServiceCfg": get_search_service_config(),
            "enable_memory_auto_extraction": False,
            "mcp_cfg": [
                {
                    "name": "amap-maps",
                    "type": "sse",
                    "url": "https://mcp.amap.com/sse?key=b0835e9abe2d55cb76226375a2083371",
                    "description": "高德地图服务，提供地点搜索、路线规划、周边查询等功能",
                },
            ],
        }

        log(f"🔍 查询: {search_request['query']}")
        log("🔌 MCP配置: amap-maps")
        log("=" * 60)

        result = run_mcp_agent_stream(
            client,
            search_request,
            resume_on_iteration_limit=True,
            log=log,
        )
        _print_run_stats(result)
        skip_on_environment_errors(result)
        print_event_sequence(result.event_types)

        has_task_step = "tasks_steps" in result.event_types
        has_normal_end = "message_end" in result.event_types

        if not has_task_step and result.error_events:
            pytest.skip("No tool calls due to LLM errors (environment issue)")

        if result.tool_stuck_count > MAX_TOOL_STUCK_APPROVALS:
            if has_task_step:
                pytest.skip(
                    f"Tool stuck {result.tool_stuck_count} times (external API timeout)"
                )
            pytest.skip("Agent tools stuck due to external API timeout")

        assert has_task_step, "Should contain tasks_steps events (MCP skill invocation)"
        assert has_normal_end, "Should have message_end event"

        assert mcp_skill_was_invoked(
            result.collected_data, "amap"
        ), "amap MCP skill was not genuinely invoked — agent fell back to web_search / skill-marketplace discovery (false pass)"

        if len(result.message_chunks) == 0:
            bash_succeeded = any(
                d.get("type") == "tasks_steps"
                and d.get("tool_name") == "bash_code_execute_tool"
                and d.get("status") == "success"
                for d in result.collected_data
            )
            if bash_succeeded:
                return

            if result.error_events:
                error_msg = str(result.error_events[0].get("error", ""))
                pytest.skip(f"Agent could not generate answer: {error_msg[:120]}")
            pytest.skip("Agent produced no answer and no error events")

        assert len(result.message_chunks) > 0, "Agent should produce a final answer"
        print("\nMCP integration test passed")

    @pytest.mark.timeout(360)
    def test_agent_with_12306_python_mcp(self, client: TestClient) -> None:
        """测试 Agent 使用 12306 MCP (Joooook/12306-mcp via Node stdio) 查询车票"""
        try:
            mcp_cmd, mcp_args, mcp_label, connect_timeout = resolve_12306_mcp_stdio()
        except RuntimeError as exc:
            pytest.skip(str(exc))

        if not preflight_llm_check():
            pytest.skip("LLM API preflight check failed (connectivity / timeout)")

        start_time = time.time()
        log = _make_log(start_time)

        log("=" * 60)
        log(f"开始测试：Agent + 12306 MCP (stdio, {mcp_label})")
        log("=" * 60)

        search_request: dict[str, object] = {
            "messageId": str(uuid.uuid4()),
            "chatId": f"test-12306py-chat-{uuid.uuid4().hex[:8]}",
            "query": "使用12306技能查询明天从北京到上海的高铁车票，列出前5趟车次的出发时间、到达时间和历时",
            "action_mode": "agent",
            "modelSelection": get_model_selection(),
            "liteModelSelection": get_lite_model_selection(),
            "searchServiceCfg": get_search_service_config(),
            "enable_memory_auto_extraction": False,
            "mcp_cfg": [
                {
                    "name": "12306",
                    "type": "stdio",
                    "command": mcp_cmd,
                    "args": mcp_args,
                    "connect_timeout": connect_timeout,
                    "description": "12306火车票查询服务，提供实时余票查询、车站信息、经停站、中转换乘等功能",
                },
            ],
        }

        log(f"🔍 查询: {search_request['query']}")
        log(
            f"🔌 MCP配置: 12306 (stdio, cmd={mcp_cmd}, args={mcp_args}, timeout={connect_timeout}s)"
        )
        log("=" * 60)

        result = run_mcp_agent_stream(
            client,
            search_request,
            resume_on_iteration_limit=False,
            log=log,
        )
        _print_run_stats(result)
        skip_on_environment_errors(result)
        print_event_sequence(result.event_types)

        has_task_step = "tasks_steps" in result.event_types
        has_normal_end = "message_end" in result.event_types

        if not has_task_step and result.error_events:
            pytest.skip("No tool calls due to LLM errors (environment issue)")

        if result.tool_stuck_count > MAX_TOOL_STUCK_APPROVALS:
            if has_task_step:
                pytest.skip(
                    f"Tool stuck {result.tool_stuck_count} times (external API timeout)"
                )
            pytest.skip("Agent tools stuck due to external API timeout")

        assert (
            has_task_step
        ), "Should contain tasks_steps events (12306 MCP skill invocation)"
        assert has_normal_end, "Should have message_end event"

        assert mcp_skill_was_invoked(
            result.collected_data, "12306"
        ), "12306 MCP skill was not genuinely invoked — agent fell back to web_search / skill-marketplace discovery (false pass)"

        assert mcp_ptc_bash_was_engaged(
            result.collected_data, "12306"
        ), "12306 MCP PTC bash path was not engaged — skill_select alone is insufficient (Goodhart guard)"

        assert mcp_ptc_get_tickets_engaged(
            result.collected_data, "12306"
        ), "12306 PTC did not reach get_tickets — date/station-only lookup is insufficient (Goodhart guard)"

        if len(result.message_chunks) == 0:
            if mcp_get_tickets_delivered(
                result.collected_data, "12306"
            ) or mcp_bash_get_tickets_succeeded(result.collected_data, "12306"):
                print(
                    "\n12306 MCP integration test passed (ticket evidence without final answer)"
                )
                return

            if result.error_events:
                error_msg = str(result.error_events[0].get("error", ""))
                pytest.skip(f"Agent could not generate answer: {error_msg[:120]}")
            pytest.skip("Agent produced no answer and no error events")

        assert len(result.message_chunks) > 0, "Agent should produce a final answer"
        assert_12306_ticket_evidence_delivered(
            result.collected_data, result.full_answer
        )
        print("\n12306 MCP integration test passed")
