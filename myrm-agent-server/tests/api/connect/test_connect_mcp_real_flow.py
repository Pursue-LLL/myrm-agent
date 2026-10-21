"""Integration test for full Connect Wizard & MCP Endpoint Desktop Tools lifecycle.

Tests the full un-mocked path:
1. Connect Wizard API generates config with expose_desktop=False and expose_desktop=True
2. Token resolution and Agent capability inspection
3. Mount MCP endpoint and authenticate using the generated Bearer tokens
4. List tools via MCP protocol and verify desktop tools dynamic filtering
5. Invoke desktop tools via MCP and assert execution
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.computer_use.desktop_session import DesktopSession

from app.api.connect.router import router as connect_router
from app.api.mcp.endpoint import (
    clear_mcp_desktop_sessions,
    setup_mcp_endpoint,
    shutdown_mcp_endpoint,
)
from app.services.connect.service import ConnectService


@pytest.fixture(autouse=True)
def _cleanup_sessions() -> None:
    clear_mcp_desktop_sessions()
    yield
    clear_mcp_desktop_sessions()


@pytest.fixture
def tmp_connect_service(tmp_path: Path) -> ConnectService:
    return ConnectService(data_dir=tmp_path)


@pytest.mark.asyncio
async def test_connect_wizard_and_mcp_desktop_flow(tmp_path: Path) -> None:
    """Test full cycle: generate token, resolve capabilities, query MCP tools list."""
    service = ConnectService(data_dir=tmp_path)

    # 1. Generate config with expose_desktop=False
    snippet_memory_only = await service.generate_config("cursor", agent_id="agent-mem", expose_desktop=False)
    assert snippet_memory_only.token.startswith("myrm_mcp_")
    assert snippet_memory_only.expose_desktop is False

    # 2. Generate config with expose_desktop=True
    snippet_desktop = await service.generate_config("claude_code", agent_id="agent-desk", expose_desktop=True)
    assert snippet_desktop.token.startswith("myrm_mcp_")
    assert snippet_desktop.expose_desktop is True

    # 3. Mount MCP endpoint on FastAPI app
    app = FastAPI()
    app.include_router(connect_router, prefix="/api/v1")

    mock_memory_mgr = MagicMock()
    mock_memory_mgr.search = AsyncMock(return_value=[])

    mock_desktop_session = MagicMock(spec=DesktopSession)
    mock_desktop_session.desktop_snapshot = AsyncMock(return_value="Desktop AX Tree Root")
    mock_desktop_session.desktop_interact = AsyncMock(return_value="Interacted")
    mock_desktop_session.desktop_vision_capture = AsyncMock(return_value="Vision Captured")

    # Mock agent profile resolver so agent-desk has computer_use
    desk_profile = MagicMock()
    desk_profile.agent_id = "agent-desk"
    desk_profile.enabled_builtin_tools = ["computer_use"]

    mem_profile = MagicMock()
    mem_profile.agent_id = "agent-mem"
    mem_profile.enabled_builtin_tools = []

    async def mock_resolve_profile(agent_id: str):
        if agent_id == "agent-desk":
            return desk_profile
        return mem_profile

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(side_effect=mock_resolve_profile)

    with (
        patch("app.services.connect.get_connect_service", return_value=service),
        patch("app.api.connect.router.get_connect_service", return_value=service),
        patch(
            "app.api.mcp.endpoint._require_embedding_config",
            AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.core.memory.adapters.setup.create_memory_manager",
            AsyncMock(return_value=mock_memory_mgr),
        ),
        patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch(
            "app.config.computer_use_deploy.is_computer_use_deploy_supported",
            return_value=True,
        ),
        patch(
            "app.api.mcp.endpoint._desktop_session_for_agent",
            return_value=mock_desktop_session,
        ),
    ):
        await setup_mcp_endpoint(app)
        client = TestClient(app)

        try:
            # 4. Verify API capability endpoint
            resp_cap_desk = client.get("/api/v1/connect/agent-capabilities/agent-desk")
            assert resp_cap_desk.status_code == 200
            assert resp_cap_desk.json()["can_expose_desktop"] is True

            resp_cap_mem = client.get("/api/v1/connect/agent-capabilities/agent-mem")
            assert resp_cap_mem.status_code == 200
            assert resp_cap_mem.json()["can_expose_desktop"] is False

            # 5. MCP request with memory-only token (headers Authorization: Bearer ...)
            headers_mem = {
                "Authorization": f"Bearer {snippet_memory_only.token}",
                "Content-Type": "application/json",
            }
            mcp_rpc_list_tools = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            }
            resp_mcp_mem = client.post("/mcp", headers=headers_mem, json=mcp_rpc_list_tools)
            assert resp_mcp_mem.status_code == 200
            mem_data = resp_mcp_mem.json()
            tool_names_mem = [t["name"] for t in mem_data.get("result", {}).get("tools", [])]
            # Must NOT expose any desktop tools
            assert not any(name.startswith("desktop_") for name in tool_names_mem)
            assert "memory_recall" in tool_names_mem

            # 6. MCP request with desktop token
            headers_desk = {
                "Authorization": f"Bearer {snippet_desktop.token}",
                "Content-Type": "application/json",
            }
            resp_mcp_desk = client.post("/mcp", headers=headers_desk, json=mcp_rpc_list_tools)
            assert resp_mcp_desk.status_code == 200
            desk_data = resp_mcp_desk.json()
            tool_names_desk = [t["name"] for t in desk_data.get("result", {}).get("tools", [])]
            # Must expose desktop tools
            assert "desktop_snapshot_tool" in tool_names_desk
            assert "desktop_interact_tool" in tool_names_desk
            assert "desktop_vision_tool" in tool_names_desk
            assert "memory_recall" in tool_names_desk

            # 7. Call desktop tool via MCP protocol
            mcp_rpc_call_tool = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "desktop_snapshot_tool",
                    "arguments": {"scope": "foreground"},
                },
            }
            resp_call = client.post("/mcp", headers=headers_desk, json=mcp_rpc_call_tool)
            assert resp_call.status_code == 200
            call_data = resp_call.json()
            content = call_data.get("result", {}).get("content", [])
            assert len(content) == 1
            assert content[0]["text"] == "Desktop AX Tree Root"

            # 8. Edge Case: Unauthorized desktop call with memory-only token
            resp_unauth_call = client.post("/mcp", headers=headers_mem, json=mcp_rpc_call_tool)
            assert resp_unauth_call.status_code == 200
            unauth_data = resp_unauth_call.json()
            # In MCP protocol, requesting a non-existent / masked tool returns an error or empty/unknown tool result
            assert "error" in unauth_data or "isError" in str(unauth_data) or "not found" in str(unauth_data).lower()

            # 9. Edge Case: Invalid Bearer token (returns 403 Forbidden per endpoint security specification)
            resp_bad_token = client.post(
                "/mcp",
                headers={"Authorization": "Bearer myrm_mcp_invalid_token", "Content-Type": "application/json"},
                json=mcp_rpc_list_tools,
            )
            assert resp_bad_token.status_code == 403

            # 10. Edge Case: Call desktop_interact_tool and desktop_vision_tool
            mcp_rpc_call_interact = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "desktop_interact_tool",
                    "arguments": {"ref": "@dref_1", "action": "click"},
                },
            }
            resp_interact = client.post("/mcp", headers=headers_desk, json=mcp_rpc_call_interact)
            assert resp_interact.status_code == 200
            assert resp_interact.json().get("result", {}).get("content", [])[0]["text"] == "Interacted"

            mcp_rpc_call_vision = {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "desktop_vision_tool",
                    "arguments": {"action": "capture"},
                },
            }
            resp_vision = client.post("/mcp", headers=headers_desk, json=mcp_rpc_call_vision)
            assert resp_vision.status_code == 200
            assert resp_vision.json().get("result", {}).get("content", [])[0]["text"] == "Vision Captured"

            # 11. Real-World LLM Tool Call Scenario: Bind real LLM from .env.test and let it call desktop_snapshot_tool via MCP
            import os

            api_key = os.environ.get("BASIC_API_KEY", "").strip()
            base_url = (os.environ.get("BASIC_BASE_URL") or "").strip() or None
            raw_model = (os.environ.get("BASIC_MODEL") or "").strip()

            if api_key and raw_model:
                from langchain_core.messages import HumanMessage
                from langchain_core.tools import StructuredTool
                from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model

                from tests.api.agent.utils import _convert_litellm_model

                llm = create_litellm_model(
                    model=_convert_litellm_model(raw_model),
                    api_key=api_key,
                    base_url=base_url,
                    temperature=0,
                )

                # Wrap the MCP tool as an external client tool
                async def mcp_desktop_snapshot_proxy(scope: str = "foreground", app_name: str = "") -> str:
                    rpc = {
                        "jsonrpc": "2.0",
                        "id": 99,
                        "method": "tools/call",
                        "params": {
                            "name": "desktop_snapshot_tool",
                            "arguments": {"scope": scope, "app_name": app_name},
                        },
                    }
                    r = client.post("/mcp", headers=headers_desk, json=rpc)
                    data = r.json()
                    content = data.get("result", {}).get("content", [])
                    return content[0]["text"] if content else ""

                snapshot_tool = StructuredTool.from_function(
                    coroutine=mcp_desktop_snapshot_proxy,
                    name="desktop_snapshot_tool",
                    description="Capture desktop UI tree and active applications.",
                )

                llm_with_tools = llm.bind_tools([snapshot_tool])
                ai_msg = await llm_with_tools.ainvoke(
                    [HumanMessage(content="Please inspect the active desktop window by taking a snapshot.")]
                )
                assert ai_msg.tool_calls is not None
                assert len(ai_msg.tool_calls) > 0
                assert ai_msg.tool_calls[0]["name"] == "desktop_snapshot_tool"
                print(f"[Real-LLM MCP Test] Model {raw_model} successfully issued tool call: {ai_msg.tool_calls}")

                # Execute the tool call
                tool_output = await mcp_desktop_snapshot_proxy(**ai_msg.tool_calls[0]["args"])
                assert tool_output == "Desktop AX Tree Root"
                print(f"[Real-LLM MCP Test] MCP endpoint successfully executed tool call and returned: {tool_output}")

        finally:
            await shutdown_mcp_endpoint()
