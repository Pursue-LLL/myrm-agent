from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.test_fast_search import perform_fast_search
from tests.api.agent.utils import check_e2e_errors


@pytest.mark.e2e
def test_scrubbing_integration(client: TestClient):
    """验证绝对路径是否在真实流中被脱敏 (Zero-Masking Value)"""
    # 强制让 Agent 打印绝对路径
    # 使用 Python 命令直接输出，明确要求执行 Python
    query = "请立即使用 python 代码执行工具打印字符串内容: '/Users/example/test_secret_path.txt'"

    full_answer, collected_data, _, _ = perform_fast_search(
        client, query, user_instructions="你必须通过运行代码来输出这个字符串，不要猜测，不要尝试读取文件。只需要打印它。"
    )

    # 检查所有事件
    raw_leak = False
    scrubbed_found = False

    for event in collected_data:
        # 遍历所有可能的文本字段
        data_str = str(event)
        if "/Users/example" in data_str:
            raw_leak = True
        if "<HOME>" in data_str:
            scrubbed_found = True

    assert not raw_leak, f"Sensitive path leaked in SSE stream! Output: {full_answer}"
    assert scrubbed_found, "Absolute path was not replaced with <HOME> placeholder in stream"


@pytest.mark.e2e
def test_circuit_breaker_integration(client: TestClient, caplog: pytest.LogCaptureFixture, tmp_path: Path):
    """验证 God-Mode 熔断注入在真实 agent 链路中生效

    物理熔断器（工具调用被 circuit breaker 拦截）的确定性验证在 harness 层
    （test_terminal_error_guard.py + test_tool_guard_terminal_chain_integration.py）。
    本用例只验证 server 端到端链路中：God-Mode 文件注入被 TerminalErrorRegistry
    读取（且 survives reset），security guardrail 消费并注入 [SYSTEM_ENFORCED]
    约束，真实 agent 会话无错误跑完——通过确定性断言，不依赖 LLM 随机输出
    （SYSTEM_ENFORCED 注入 LLM prompt，不会出现在 SSE 事件中；模型是否复述
    约束取决于模型行为，不能作为断言依据）。使用 tmp_path 唯一路径，避免
    并行 pytest 进程共享固定路径文件的竞态。
    """
    import logging
    import os

    from myrm_agent_harness.agent.middlewares._session_context import (
        get_terminal_errors,
        reset_terminal_errors,
    )

    storage_path = tmp_path / ".myrm_terminal_errors.json"
    storage_path.write_text('["network_blocked"]', encoding="utf-8")
    os.environ["MYRM_TERMINAL_ERRORS_PATH"] = str(storage_path)

    try:
        # 核心确定性断言：God-Mode 文件注入 survives reset（历史 bug 修复点）
        reset_terminal_errors()
        assert "network_blocked" in get_terminal_errors().get_all(), (
            "God-Mode file injection must survive reset_terminal_errors()"
        )

        query = "搜索一下 2026 年的 AI 预测"
        with caplog.at_level(
            logging.INFO,
            logger="myrm_agent_harness.agent.middlewares.security.security_guardrail_middleware",
        ):
            _, collected_data, _, _ = perform_fast_search(client, query)

        check_e2e_errors(collected_data)

        injected = [r.getMessage() for r in caplog.records if "Circuit breaker cognition injected" in r.getMessage()]
        assert injected, (
            "God-Mode 'network_blocked' injection was not consumed by the security guardrail middleware in the real agent chain"
        )

    finally:
        os.environ.pop("MYRM_TERMINAL_ERRORS_PATH", None)
