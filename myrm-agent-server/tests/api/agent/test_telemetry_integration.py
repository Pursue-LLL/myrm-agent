import pytest
from fastapi.testclient import TestClient

from tests.api.agent.test_fast_search import perform_fast_search
from tests.api.agent.utils import check_e2e_errors


@pytest.mark.e2e
def test_scrubbing_integration(client: TestClient):
    """验证绝对路径是否在真实流中被脱敏 (Zero-Masking Value)"""
    # 强制让 Agent 打印绝对路径
    # 使用 Python 命令直接输出，明确要求执行 Python
    query = "请立即使用 python 代码执行工具打印字符串内容: '/Users/yululiu/test_secret_path.txt'"

    full_answer, collected_data, _, _ = perform_fast_search(
        client, query, user_instructions="你必须通过运行代码来输出这个字符串，不要猜测，不要尝试读取文件。只需要打印它。"
    )

    # 检查所有事件
    raw_leak = False
    scrubbed_found = False

    for event in collected_data:
        # 遍历所有可能的文本字段
        data_str = str(event)
        if "/Users/yululiu" in data_str:
            raw_leak = True
        if "<HOME>" in data_str:
            scrubbed_found = True

    assert not raw_leak, f"Sensitive path leaked in SSE stream! Output: {full_answer}"
    assert scrubbed_found, "Absolute path was not replaced with <HOME> placeholder in stream"


@pytest.mark.e2e
def test_circuit_breaker_integration(client: TestClient):
    """验证物理熔断器是否生效并返回正确元数据 (Circuit Breaker Value)"""
    import os
    from pathlib import Path

    # 物理注入：直接写文件到临时目录，并通过环境变量强制对齐
    storage_path = Path(os.getcwd()) / ".myrm_test_circuit_breaker.json"
    storage_path.write_text('["network_blocked"]', encoding="utf-8")

    # 注入环境变量，让 Server 进程也能感知
    os.environ["MYRM_TERMINAL_ERRORS_PATH"] = str(storage_path)

    try:
        # 强制触发搜索
        query = "搜索一下 2026 年的 AI 预测"

        full_answer, collected_data, _, _ = perform_fast_search(client, query)

        check_e2e_errors(collected_data)

        blocked_by_system = False
        for event in collected_data:
            err = str(event)
            if "[SYSTEM_ENFORCED]" in err or "network_blocked" in err:
                blocked_by_system = True

        assert blocked_by_system, "Circuit breaker failed to block even with God-Mode environment variable present"

    finally:
        os.environ.pop("MYRM_TERMINAL_ERRORS_PATH", None)
        if storage_path.exists():
            storage_path.unlink()
