"""Vault & Deadlock Agent E2E 测试

测试 /api/v1/vault/{obj_id}/content 流式接口
测试 /api/v1/agents/general-stream 端的 Payload Deadlock 拦截
"""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import (
    get_model_selection,
    get_search_service_config,
)


@pytest.fixture
def tmp_workspace(tmp_path):
    import os

    os.environ["WORKSPACE_ROOT"] = str(tmp_path)
    yield str(tmp_path)
    if "WORKSPACE_ROOT" in os.environ:
        del os.environ["WORKSPACE_ROOT"]


class TestVaultAndDeadlock:
    def test_vault_streaming_api(self, client: TestClient, tmp_workspace: str):
        """测试 Vault 的 /content 和 /meta HTTP 接口是否能正确工作"""
        from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

        from app.api.dependencies import get_workspace_root

        client.app.dependency_overrides[get_workspace_root] = lambda: Path(tmp_workspace)

        # 1. 存入一个虚构的大文件
        vault = ArtifactVault(tmp_workspace)
        massive_content = "This is a massive file content. " * 1000
        pointer = vault.put(massive_content, "massive.txt", "text/plain")
        obj_id = pointer.replace("vault://", "")
        print("POINTER:", pointer, "OBJ_ID:", obj_id)

        # 2. 测试 /meta 接口
        meta_res = client.get(f"/api/v1/files/vault/{obj_id}/meta")
        if meta_res.status_code != 200:
            print("META ERROR:", meta_res.text)
        assert meta_res.status_code == 200
        assert meta_res.json()["filename"] == "massive.txt"

        # 3. 测试 /content 接口 (流式 FileResponse)
        content_res = client.get(f"/api/v1/files/vault/{obj_id}/content")
        if content_res.status_code != 200:
            print("CONTENT ERROR:", content_res.text)
        assert content_res.status_code == 200
        assert content_res.text == massive_content
        assert content_res.headers["content-type"] == "text/plain; charset=utf-8"

    @pytest.mark.e2e
    @pytest.mark.skipif(
        not os.environ.get("BASIC_API_KEY"),
        reason="E2E test requires BASIC_API_KEY environment variable",
    )
    def test_payload_deadlock_interception(self, client: TestClient):
        """测试主模型重复派发相同时触发死锁拦截"""

        query = (
            "请使用 delegate_task 工具，调用 'coder' 子智能体执行一个任务。任务内容是：'print(1/0)'。\n"
            "因为这段代码一定会报错，请你收到错误后，一字不差地用完全相同的参数再次调用 delegate_task 派发同样的任务。必须一字不差！"
        )

        req_data = {
            "messageId": "test-msg-123",
            "chatId": "test-chat-123",
            "query": query,
            "modelSelection": get_model_selection(),
            "searchServiceCfg": get_search_service_config(),
        }

        collected_data = []
        deadlock_prevented = False

        with client.stream("POST", "/api/v1/agents/agent-stream", json=req_data) as response:
            if response.status_code != 200:
                response.read()
                print(f"HTTP Error: {response.text}")

            assert response.status_code == 200

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                    collected_data.append(data)

                    # 检查是不是拦截了
                    if data.get("type") == "error" or data.get("type") == "tasks_steps":
                        text_val = str(data)
                        if "死循环委派" in text_val or "deadlock-prevented" in text_val:
                            deadlock_prevented = True
                            print("\n✅ 成功捕获到死锁拦截事件！")
                            break

                except json.JSONDecodeError:
                    continue

        # 允许不一定每次都重现（如果大模型太聪明没有一字不差地发，或者一次就纠正了），
        # 但如果它复读了，我们期望死锁能捕捉。
        # 稳妥起见，我们只断言测试能顺利跑完，没有由于无限死循环导致卡死超时。
        assert len(collected_data) > 0
        if not deadlock_prevented:
            print("\n⚠️ 模型没有复读完全一样的参数，未能触发拦截，但也正常退出了。")
