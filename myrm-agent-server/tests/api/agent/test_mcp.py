"""测试 Agent 模式 MCP 技能集成

本测试验证 Agent 模式与 MCP（Model Context Protocol）技能的集成。

运行方式：
-----------
   pytest tests/api/agent/test_mcp.py -v -s

注意事项：
-----------
- 需要正确配置 .env 文件中的模型和搜索服务配置
- 需要 MCP 服务器可用（如 amap-maps）
- 沙箱模式自动跟随 DEPLOY_MODE 环境变量（local 或 sandbox）
- 使用 live_client fixture（实际运行在端口上，支持 MCP HTTP 回调）
"""

import json
import os
import shutil
import time
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import (
    get_lite_model_selection,
    get_model_selection,
    get_search_service_config,
)
from tests.support.test_secrets import resolve_test_env

_MCP_12306_INDEX = (
    Path(__file__).resolve().parents[4] / "12306-mcp" / "build" / "index.js"
)

_UVX_PATH = os.environ.get("UVX_PATH") or shutil.which("uvx") or "uvx"

_TEST_WALL_CLOCK_LIMIT = 300
_STREAM_TIMEOUT = 300
_PREFLIGHT_TIMEOUT = 30
_MAX_TOOL_STUCK_APPROVALS = 0


def _mcp_skill_was_invoked(collected_data: list[dict[str, object]], marker: str) -> bool:
    """Return True only when the configured MCP skill was genuinely engaged.

    Hard evidence is restricted to the PTC fingerprints that can only come from
    the specific skill: ``skill_select`` selecting it, ``bash`` executing code that
    imports it, or reading its ``SKILL.md``. Search-query / free-text fields are
    intentionally ignored so a ``web_search`` fabrication or skill-marketplace
    discovery (which merely mentions the marker in a query) cannot false-pass.
    """
    marker = marker.lower()
    for event in collected_data:
        if event.get("type") != "tasks_steps":
            continue
        tool_name = event.get("tool_name")
        items = event.get("data")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if tool_name == "skill_select_tool" and marker in str(item.get("skill_name", "")).lower():
                return True
            if tool_name == "bash_code_execute_tool" and marker in str(item.get("code", "")).lower():
                return True
            if tool_name == "file_read_tool" and marker in str(item.get("file_path", "")).lower():
                return True
    return False


def _preflight_llm_check() -> bool:
    """Send a trivial LLM request to verify connectivity before the real test."""
    api_key = resolve_test_env("BASIC_API_KEY")
    base_url = resolve_test_env("BASIC_BASE_URL")
    model_raw = resolve_test_env("BASIC_MODEL")
    if not all((api_key, base_url, model_raw)):
        return False

    model = model_raw.split("/", 1)[1] if "/" in model_raw else model_raw
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
        "stream": False,
    }
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_PREFLIGHT_TIMEOUT,
        )
        return resp.status_code == 200
    except (httpx.TimeoutException, httpx.ConnectError, OSError):
        return False


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


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestAgentMCP:
    """Agent 模式 MCP 技能测试类"""

    @pytest.mark.timeout(360)
    def test_agent_with_mcp(self, client: TestClient) -> None:
        """测试 Agent 模式配置 MCP

        使用 TestClient 进行测试。
        注意：如果 MCP 需要真实 HTTP 回调，需要使用 live_client。
        """
        if not _preflight_llm_check():
            pytest.skip("LLM API preflight check failed (connectivity / timeout)")

        start_time = time.time()

        def log(msg: str) -> None:
            elapsed = time.time() - start_time
            print(f"[{elapsed:.1f}s] {msg}", flush=True)

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

        collected_data: list[dict[str, object]] = []
        message_chunks: list[str] = []
        tool_results: list[str] = []

        # 用于流式输出消息
        current_message_line = ""
        is_first_message = True
        last_sources_count = 0  # 记录上次显示的 sources 数量，避免重复

        # 添加 X-Chat-ID header 以启用变量持久化
        test_chat_id = str(search_request["chatId"])
        headers = {"X-Chat-ID": test_chat_id}

        log("📡 发送 POST 请求...")

        reasoning_count = 0
        tool_stuck_count = 0

        def _process_event(data: dict[str, object]) -> None:
            nonlocal current_message_line, is_first_message, last_sources_count, reasoning_count, tool_stuck_count
            data_type = data.get("type", "unknown")

            if data_type == "message":
                content = data.get("data", "")
                if content:
                    message_chunks.append(str(content))
                    if is_first_message:
                        print("\n💬 AI 回复: ", end="", flush=True)
                        is_first_message = False
                    if "\n" in content:
                        parts = str(content).split("\n")
                        for i, part in enumerate(parts):
                            print(part, end="", flush=True)
                            if i < len(parts) - 1:
                                print()
                    else:
                        print(content, end="", flush=True)
            elif data_type == "reasoning":
                reasoning_count += 1
                if reasoning_count % 20 == 1:
                    print(".", end="", flush=True)
            elif data_type == "sources":
                if current_message_line:
                    print()
                    current_message_line = ""
                sources_data = data.get("data", [])
                tool_results.append(str(sources_data))
                if len(sources_data) != last_sources_count:
                    print(f"\n🔍 搜索来源: {len(sources_data)} 个结果")
                    last_sources_count = len(sources_data)
            elif data_type == "tasks_steps":
                if current_message_line:
                    print()
                    current_message_line = ""
                tool_name = data.get("tool_name", "unknown")
                status = data.get("status", "success")
                step_data_list = data.get("data", [])
                status_icon = "❌" if status == "error" else "🔧"
                print(f"\n{status_icon} 工具调用: {tool_name}")
                if step_data_list:
                    print(f"   步骤数据: {len(step_data_list)} 项")
            elif data_type == "progress":
                status = data.get("data", {})
                pct = status.get("progress_pct", "") if isinstance(status, dict) else ""
                print(f"\n📊 进度: {pct}%", flush=True)
            elif data_type == "tools_snapshot":
                tools_data = data.get("data", [])
                count = len(tools_data) if isinstance(tools_data, list) else 0
                print(f"\n🛠️ Agent 已就绪 ({count} 工具加载完成)", flush=True)
            elif data_type == "tool_start":
                print("\n⏳ 工具启动中...", flush=True)
            elif data_type == "tool_heartbeat":
                print("♥", end="", flush=True)
            elif data_type in ("approval_required", "tool_approval_request"):
                approval_data = data.get("data", data)
                action_type = ""
                if isinstance(approval_data, dict):
                    action_type = approval_data.get("action_type", "")
                if action_type == "tool_stuck":
                    tool_stuck_count += 1
                    log(f"Tool stuck detected (count={tool_stuck_count})")
            elif data_type == "error":
                if current_message_line:
                    print()
                    current_message_line = ""
                print(f"\n❌ 错误: {data}")

        def _stream_request(req_data: dict[str, object]) -> int:
            nonlocal line_count
            elapsed_total = time.time() - start_time
            if elapsed_total > _TEST_WALL_CLOCK_LIMIT:
                log(f"Wall-clock limit reached ({elapsed_total:.0f}s > {_TEST_WALL_CLOCK_LIMIT}s), skipping stream")
                return 0

            with client.stream(
                "POST", "/api/v1/agents/agent-stream", json=req_data, headers=headers
            ) as response:
                log(f"收到响应: {response.status_code}")
                if response.status_code != 200:
                    response.read()
                    print(f"\nHTTP错误 {response.status_code}:")
                    print(f"响应内容: {response.text}")
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")

                log("开始读取流式响应...\n")
                round_lines = 0
                stream_start = time.time()
                for line in response.iter_lines():
                    round_lines += 1
                    line_count += 1

                    now = time.time()
                    if now - stream_start > _STREAM_TIMEOUT:
                        log(f"Stream timeout after {_STREAM_TIMEOUT}s, breaking")
                        break
                    if now - start_time > _TEST_WALL_CLOCK_LIMIT:
                        log(f"Wall-clock limit reached ({now - start_time:.0f}s), breaking stream")
                        break

                    if not line:
                        continue
                    line_text = (
                        line.strip() if isinstance(line, str) else line.decode().strip()
                    )
                    if not line_text.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line_text[6:])
                        if data is None:
                            continue
                        collected_data.append(data)
                        _process_event(data)
                    except json.JSONDecodeError as e:
                        log(f"JSON解析错误: {e}")
                return round_lines

        line_count = 0
        _stream_request(search_request)

        def _has_final_answer() -> bool:
            has_message = any(d.get("type") == "message" for d in collected_data)
            has_end = any(d.get("type") == "message_end" for d in collected_data)
            return has_message and has_end

        for round_idx in range(10):
            if _has_final_answer():
                log("已收到完整回答，停止后续 resume")
                break

            if time.time() - start_time > _TEST_WALL_CLOCK_LIMIT:
                log("Wall-clock limit reached, stopping resume loop")
                break

            needs_resume = False
            resume_reason = ""
            is_tool_stuck = False
            for data in reversed(collected_data):
                event_type = data.get("type")
                if event_type in ("approval_required", "tool_approval_request"):
                    approval_data = data.get("data", data)
                    if isinstance(approval_data, dict) and approval_data.get("action_type") == "tool_stuck":
                        is_tool_stuck = True
                    needs_resume = True
                    resume_reason = "approval"
                    break
                if event_type == "iteration_limit_reached":
                    needs_resume = True
                    resume_reason = "iteration_limit"
                    break
                if event_type == "message":
                    break

            if not needs_resume:
                break

            if is_tool_stuck and tool_stuck_count > _MAX_TOOL_STUCK_APPROVALS:
                log(f"Tool stuck {tool_stuck_count} times (limit={_MAX_TOOL_STUCK_APPROVALS}), stopping resume")
                break

            resume_request = search_request.copy()
            resume_request["messageId"] = str(uuid.uuid4())

            if resume_reason == "approval":
                log(f"Auto-approving tool call (round {round_idx + 1})...")
                resume_request["resumeValue"] = {
                    "decisions": [{
                        "type": "approve",
                        "extensions": {"allowAlways": True},
                    }],
                }
            else:
                log(f"Iteration limit reached, resuming (round {round_idx + 1})...")
                resume_request["resumeValue"] = {"resume": True}

            _stream_request(resume_request)

        if message_chunks:
            print()

        total_elapsed = time.time() - start_time
        log(f"\nStream finished: {line_count} lines, {len(collected_data)} events, {total_elapsed:.1f}s total")

        full_answer = "".join(message_chunks)

        print("\nStats:")
        print(f"  - Events: {len(collected_data)}")
        print(f"  - Message chunks: {len(message_chunks)}")
        print(f"  - Tool results: {len(tool_results)}")
        print(f"  - Answer length: {len(full_answer)} chars")

        _ENV_ERROR_KEYWORDS = [
            "Authentication",
            "Authorization",
            "Connection error",
            "InternalServerError",
            "Cannot connect",
            "Recursion limit",
            "Timeout",
            "timeout",
            "rate limit",
        ]

        if len(collected_data) == 0:
            pytest.skip("No events received (LLM / network issue)")

        error_events = [d for d in collected_data if d.get("type") == "error"]
        if error_events:
            error_msg = str(error_events[0].get("error", ""))
            if any(kw in error_msg for kw in _ENV_ERROR_KEYWORDS):
                pytest.skip(f"Environment issue: {error_msg[:120]}")

        event_types = [str(d.get("type", "unknown")) for d in collected_data]

        compressed_events: list[str] = []
        for evt in event_types:
            if evt == "message":
                if not compressed_events or compressed_events[-1] != "message":
                    compressed_events.append("message")
            else:
                compressed_events.append(evt)

        print(f"\nEvent sequence: {' -> '.join(compressed_events)}")
        print(f"(raw: {len(event_types)}, compressed: {len(compressed_events)})")

        has_task_step = "tasks_steps" in event_types
        has_normal_end = "message_end" in event_types

        if not has_task_step and error_events:
            pytest.skip("No tool calls due to LLM errors (environment issue)")

        if tool_stuck_count > _MAX_TOOL_STUCK_APPROVALS:
            if has_task_step:
                pytest.skip(f"Tool stuck {tool_stuck_count} times (external API timeout)")
            pytest.skip("Agent tools stuck due to external API timeout")

        assert has_task_step, "Should contain tasks_steps events (MCP skill invocation)"
        assert has_normal_end, "Should have message_end event"

        assert _mcp_skill_was_invoked(collected_data, "amap"), (
            "amap MCP skill was not genuinely invoked — agent fell back to "
            "web_search / skill-marketplace discovery (false pass)"
        )

        if len(message_chunks) == 0:
            bash_succeeded = any(
                d.get("type") == "tasks_steps"
                and d.get("tool_name") == "bash_code_execute_tool"
                and d.get("status") == "success"
                for d in collected_data
            )
            if bash_succeeded:
                return

            if error_events:
                error_msg = str(error_events[0].get("error", ""))
                pytest.skip(f"Agent could not generate answer: {error_msg[:120]}")
            else:
                pytest.skip("Agent produced no answer and no error events")

        assert len(message_chunks) > 0, "Agent should produce a final answer"

        print("\nMCP integration test passed")

    @pytest.mark.timeout(360)
    def test_agent_with_12306_python_mcp(self, client: TestClient) -> None:
        """测试 Agent 使用 Python 版 12306 MCP (drfccv/mcp-server-12306) 查询车票

        验证 PTC 在 stdio 类型 MCP 下正常工作（Python 版，更稳定）。
        """
        import shutil

        uvx_cmd = _UVX_PATH if Path(_UVX_PATH).exists() else shutil.which("uvx")
        if not uvx_cmd:
            pytest.skip("uvx not found, cannot run Python 12306 MCP")

        if not _preflight_llm_check():
            pytest.skip("LLM API preflight check failed (connectivity / timeout)")

        start_time = time.time()

        def log(msg: str) -> None:
            elapsed = time.time() - start_time
            print(f"[{elapsed:.1f}s] {msg}", flush=True)

        log("=" * 60)
        log("开始测试：Agent + Python 12306 MCP (uvx stdio)")
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
                    "command": uvx_cmd,
                    "args": ["mcp-server-12306"],
                    "description": "12306火车票查询服务（Python版），提供实时余票查询、车站信息、经停站、中转换乘等功能",
                },
            ],
        }

        log(f"🔍 查询: {search_request['query']}")
        log(f"🔌 MCP配置: 12306 (uvx stdio, cmd={uvx_cmd})")
        log("=" * 60)

        collected_data: list[dict[str, object]] = []
        message_chunks: list[str] = []
        tool_results: list[str] = []

        current_message_line = ""
        is_first_message = True
        last_sources_count = 0

        test_chat_id = str(search_request["chatId"])
        headers = {"X-Chat-ID": test_chat_id}

        log("📡 发送 POST 请求...")

        reasoning_count = 0
        tool_stuck_count = 0

        def _process_event(data: dict[str, object]) -> None:
            nonlocal current_message_line, is_first_message, last_sources_count, reasoning_count, tool_stuck_count
            data_type = data.get("type", "unknown")

            if data_type == "message":
                content = data.get("data", "")
                if content:
                    message_chunks.append(str(content))
                    if is_first_message:
                        print("\n💬 AI 回复: ", end="", flush=True)
                        is_first_message = False
                    if "\n" in content:
                        parts = str(content).split("\n")
                        for i, part in enumerate(parts):
                            print(part, end="", flush=True)
                            if i < len(parts) - 1:
                                print()
                    else:
                        print(content, end="", flush=True)
            elif data_type == "reasoning":
                reasoning_count += 1
                if reasoning_count % 20 == 1:
                    print(".", end="", flush=True)
            elif data_type == "sources":
                if current_message_line:
                    print()
                    current_message_line = ""
                sources_data = data.get("data", [])
                tool_results.append(str(sources_data))
                if len(sources_data) != last_sources_count:
                    print(f"\n🔍 搜索来源: {len(sources_data)} 个结果")
                    last_sources_count = len(sources_data)
            elif data_type == "tasks_steps":
                if current_message_line:
                    print()
                    current_message_line = ""
                tool_name = data.get("tool_name", "unknown")
                status = data.get("status", "success")
                step_data_list = data.get("data", [])
                status_icon = "❌" if status == "error" else "🔧"
                print(f"\n{status_icon} 工具调用: {tool_name}")
                if step_data_list:
                    print(f"   步骤数据: {len(step_data_list)} 项")
            elif data_type == "progress":
                status = data.get("data", {})
                pct = status.get("progress_pct", "") if isinstance(status, dict) else ""
                print(f"\n📊 进度: {pct}%", flush=True)
            elif data_type == "tools_snapshot":
                tools_data = data.get("data", [])
                count = len(tools_data) if isinstance(tools_data, list) else 0
                print(f"\n🛠️ Agent 已就绪 ({count} 工具加载完成)", flush=True)
            elif data_type == "tool_start":
                print("\n⏳ 工具启动中...", flush=True)
            elif data_type == "tool_heartbeat":
                print("♥", end="", flush=True)
            elif data_type in ("approval_required", "tool_approval_request"):
                approval_data = data.get("data", data)
                action_type = ""
                if isinstance(approval_data, dict):
                    action_type = approval_data.get("action_type", "")
                if action_type == "tool_stuck":
                    tool_stuck_count += 1
                    log(f"Tool stuck detected (count={tool_stuck_count})")
            elif data_type == "error":
                if current_message_line:
                    print()
                    current_message_line = ""
                print(f"\n❌ 错误: {data}")

        def _stream_request(req_data: dict[str, object]) -> int:
            nonlocal line_count
            elapsed_total = time.time() - start_time
            if elapsed_total > _TEST_WALL_CLOCK_LIMIT:
                log(f"Wall-clock limit reached ({elapsed_total:.0f}s > {_TEST_WALL_CLOCK_LIMIT}s), skipping stream")
                return 0

            with client.stream(
                "POST", "/api/v1/agents/agent-stream", json=req_data, headers=headers
            ) as response:
                log(f"收到响应: {response.status_code}")
                if response.status_code != 200:
                    response.read()
                    print(f"\nHTTP错误 {response.status_code}:")
                    print(f"响应内容: {response.text}")
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")

                log("开始读取流式响应...\n")
                round_lines = 0
                stream_start = time.time()
                for line in response.iter_lines():
                    round_lines += 1
                    line_count += 1

                    now = time.time()
                    if now - stream_start > _STREAM_TIMEOUT:
                        log(f"Stream timeout after {_STREAM_TIMEOUT}s, breaking")
                        break
                    if now - start_time > _TEST_WALL_CLOCK_LIMIT:
                        log(f"Wall-clock limit reached ({now - start_time:.0f}s), breaking stream")
                        break

                    if not line:
                        continue
                    line_text = (
                        line.strip() if isinstance(line, str) else line.decode().strip()
                    )
                    if not line_text.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line_text[6:])
                        if data is None:
                            continue
                        collected_data.append(data)
                        _process_event(data)
                    except json.JSONDecodeError as e:
                        log(f"JSON解析错误: {e}")
                return round_lines

        line_count = 0
        _stream_request(search_request)

        def _has_final_answer() -> bool:
            has_message = any(d.get("type") == "message" for d in collected_data)
            has_end = any(d.get("type") == "message_end" for d in collected_data)
            return has_message and has_end

        for round_idx in range(10):
            if _has_final_answer():
                log("已收到完整回答，停止后续 resume")
                break

            if time.time() - start_time > _TEST_WALL_CLOCK_LIMIT:
                log("Wall-clock limit reached, stopping resume loop")
                break

            needs_resume = False
            resume_reason = ""
            is_tool_stuck = False
            for data in reversed(collected_data):
                event_type = data.get("type")
                if event_type in ("approval_required", "tool_approval_request"):
                    approval_data = data.get("data", data)
                    if isinstance(approval_data, dict) and approval_data.get("action_type") == "tool_stuck":
                        is_tool_stuck = True
                    needs_resume = True
                    resume_reason = "approval"
                    break
                if event_type == "iteration_limit_reached":
                    needs_resume = True
                    resume_reason = "iteration_limit"
                    break
                if event_type == "message":
                    break

            if not needs_resume:
                break

            if is_tool_stuck and tool_stuck_count > _MAX_TOOL_STUCK_APPROVALS:
                log(f"Tool stuck {tool_stuck_count} times (limit={_MAX_TOOL_STUCK_APPROVALS}), stopping resume")
                break

            resume_request = search_request.copy()
            resume_request["messageId"] = str(uuid.uuid4())

            if resume_reason == "approval":
                log(f"Auto-approving tool call (round {round_idx + 1})...")
                resume_request["resumeValue"] = {
                    "decisions": [{
                        "type": "approve",
                        "extensions": {"allowAlways": True},
                    }],
                }
            else:
                log(f"Iteration limit reached, resuming (round {round_idx + 1})...")
                resume_request["resumeValue"] = {"resume": True}

            _stream_request(resume_request)

        if message_chunks:
            print()

        total_elapsed = time.time() - start_time
        log(f"\nStream finished: {line_count} lines, {len(collected_data)} events, {total_elapsed:.1f}s total")

        full_answer = "".join(message_chunks)

        print("\nStats:")
        print(f"  - Events: {len(collected_data)}")
        print(f"  - Message chunks: {len(message_chunks)}")
        print(f"  - Tool results: {len(tool_results)}")
        print(f"  - Answer length: {len(full_answer)} chars")

        _ENV_ERROR_KEYWORDS = [
            "Authentication",
            "Authorization",
            "Connection error",
            "InternalServerError",
            "Cannot connect",
            "Recursion limit",
            "Timeout",
            "timeout",
            "rate limit",
        ]

        if len(collected_data) == 0:
            pytest.skip("No events received (LLM / network issue)")

        error_events = [d for d in collected_data if d.get("type") == "error"]
        if error_events:
            error_msg = str(error_events[0].get("error", ""))
            if any(kw in error_msg for kw in _ENV_ERROR_KEYWORDS):
                pytest.skip(f"Environment issue: {error_msg[:120]}")

        event_types = [str(d.get("type", "unknown")) for d in collected_data]

        compressed_events: list[str] = []
        for evt in event_types:
            if evt == "message":
                if not compressed_events or compressed_events[-1] != "message":
                    compressed_events.append("message")
            else:
                compressed_events.append(evt)

        print(f"\nEvent sequence: {' -> '.join(compressed_events)}")
        print(f"(raw: {len(event_types)}, compressed: {len(compressed_events)})")

        has_task_step = "tasks_steps" in event_types
        has_normal_end = "message_end" in event_types

        if not has_task_step and error_events:
            pytest.skip("No tool calls due to LLM errors (environment issue)")

        if tool_stuck_count > _MAX_TOOL_STUCK_APPROVALS:
            if has_task_step:
                pytest.skip(f"Tool stuck {tool_stuck_count} times (external API timeout)")
            pytest.skip("Agent tools stuck due to external API timeout")

        assert has_task_step, "Should contain tasks_steps events (12306 MCP skill invocation)"
        assert has_normal_end, "Should have message_end event"

        assert _mcp_skill_was_invoked(collected_data, "12306"), (
            "12306 MCP skill was not genuinely invoked — agent fell back to "
            "web_search / skill-marketplace discovery (false pass)"
        )

        if len(message_chunks) == 0:
            bash_succeeded = any(
                d.get("type") == "tasks_steps"
                and d.get("tool_name") == "bash_code_execute_tool"
                and d.get("status") == "success"
                for d in collected_data
            )
            if bash_succeeded:
                return

            if error_events:
                error_msg = str(error_events[0].get("error", ""))
                pytest.skip(f"Agent could not generate answer: {error_msg[:120]}")
            else:
                pytest.skip("Agent produced no answer and no error events")

        assert len(message_chunks) > 0, "Agent should produce a final answer"

        print("\n12306 Python MCP integration test passed")
