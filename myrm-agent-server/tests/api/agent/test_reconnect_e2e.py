"""客户端断线重连测试 (Persistent Server/Client 模式)

验证 OfflineDurableTask 和 GlobalStreamRegistry 机制在实际掉线和恢复时的表现。
"""

import asyncio
import os
import uuid
from typing import AsyncGenerator

import httpx
import pytest

from tests.api.agent.utils import (
    get_model_selection,
    get_search_service_config,
)

BASE_URL = os.environ.get("API_URL", "http://127.0.0.1:8080")
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {os.environ.get('BASIC_API_KEY', 'dummy')}",
}


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """使用真实的 HTTP 客户端连接外部或本地运行的服务器"""
    async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=120.0) as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
async def test_agent_stream_disconnect_and_reconnect(
    async_client: httpx.AsyncClient,
) -> None:
    """测试长运行任务(agentic_search)中途断开连接，随后使用Last-Event-ID恢复连接"""
    chat_id = f"test-reconnect-{uuid.uuid4().hex[:8]}"
    message_id = f"msg-{uuid.uuid4().hex[:8]}"

    payload = {
        "query": "Please count from 1 to 10 slowly, one number per sentence.",
        "chatId": chat_id,
        "messageId": message_id,
        "actionMode": "agentic_search",
        "modelSelection": get_model_selection(),
        "searchServiceCfg": get_search_service_config(),
    }

    url = "/api/v1/agents/agent-stream"

    print(f"\n[Test] 开始发起首个连接... chat_id={chat_id}")

    last_event_id = None
    chunks_received = 0

    # ==========================
    # 1. 模拟首次请求并中途强制断开
    # ==========================
    try:
        async with async_client.stream("POST", url, json=payload, timeout=20.0) as response:
            if response.status_code != 200:
                print(f"\n[Test] 首次连接已中断（符合预期）: Expected 200, got {response.status_code}")
                err_text = await response.aread()
                print(f"Error text: {err_text}")
                assert response.status_code == 200, f"Expected 200, got {response.status_code}"

            async for chunk in response.aiter_text():
                if chunk.strip():
                    chunks_received += 1

                    # 捕获 Last-Event-ID
                    if "id:" in chunk:
                        for line in chunk.split("\n"):
                            if line.startswith("id:"):
                                last_event_id = line[3:].strip()

                    # 接收到3个有效chunk后，我们主动引发异常/Break来强制关闭这个流连接
                    if chunks_received >= 3:
                        print(f"\n[Test] 收到第 {chunks_received} 个数据块，准备断开连接...")
                        break
    except Exception as e:
        print(f"\n[Test] 首次连接已中断（符合预期）: {e}")

    assert chunks_received >= 3, "未能成功接收到初期的 SSE 数据流"

    # 我们等待一段时间，让后台任务（OfflineDurableTask）有机会在没有客户端的情况下继续运行
    print("\n[Test] 等待2秒钟让后台进程继续执行...")
    await asyncio.sleep(2)

    # ==========================
    # 2. 模拟客户端带着 Last-Event-ID 重连
    # ==========================
    headers = {}
    if last_event_id:
        headers["Last-Event-ID"] = last_event_id

    print(f"\n[Test] 带着 Last-Event-ID ({last_event_id}) 发起重连请求...")

    reconnect_chunks = 0
    task_completed = False

    # 因为这是新的请求，我们需要一个新的 httpx context
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client_resume:
        async with client_resume.stream("POST", url, json=payload, headers=headers) as response:
            # 重连如果不导致500，说明 UNIQUE 冲突已解决
            assert response.status_code == 200, (
                f"Reconnect expected 200, got {response.status_code}. Possible DB UNIQUE constraint conflict!"
            )

            async for chunk in response.aiter_text():
                if chunk.strip():
                    print(f"[RECONNECT CHUNK] {chunk}")
                    reconnect_chunks += 1
                    if "message_completed" in chunk or "task_completed" in chunk or "DONE" in chunk or "message_end" in chunk:
                        task_completed = True

    print(f"\n[Test] 重连后收到了 {reconnect_chunks} 个数据块。")
    assert task_completed, "重连后未收到任务完成的信号！任务可能死在后台了。"
    print("\n✅ 测试通过：客户端断线重连恢复逻辑 (Persistent Server) 运行完美，无数据冲突。")
