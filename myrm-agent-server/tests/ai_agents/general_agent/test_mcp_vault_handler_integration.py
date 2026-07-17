"""Integration tests for MCP vault handler injection chain.

Verifies the full injection path:
factory.py → MCPServerConfig.model_copy → session_actor → process_session_tools

Key paths tested WITHOUT mocking:
- build_mcp_vault_handler creates a real handler that writes to ArtifactVault
- MCPServerConfig accepts handler via model_copy (frozen model constraint)
- Handler end-to-end: content → vault storage → vault:// pointer → file_read_tool retrieval
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestVaultHandlerInjectionChain:
    """Test factory → config → handler injection chain with real components."""

    def test_factory_injection_pattern(self, tmp_path: Path) -> None:
        """Verify the exact pattern used in factory.py works end-to-end."""
        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler
        from app.core.types.business import MCPServerConfig

        configs = [
            MCPServerConfig(name="server_a", type="stdio", command="echo"),
            MCPServerConfig(name="server_b", type="stdio", command="cat"),
        ]

        workspace_root = str(tmp_path)
        vault_handler = build_mcp_vault_handler(workspace_root)
        updated_configs = [
            cfg.model_copy(update={"oversized_result_handler": vault_handler})
            for cfg in configs
        ]

        for cfg in updated_configs:
            assert cfg.oversized_result_handler is vault_handler

        for original in configs:
            assert original.oversized_result_handler is None

    def test_handler_e2e_vault_roundtrip(self, tmp_path: Path) -> None:
        """End-to-end: handler stores content → vault → pointer → retrieval."""
        from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))
        content = "INTEGRATION_TEST_" * 5_000  # ~85K chars
        result = handler(content, "mcp__test_server__big_query")

        assert result is not None
        assert "vault://" in result
        assert "file_read_tool" in result
        assert "Full result stored in vault" in result

        vault_start = result.index("vault://")
        vault_end = result.index("]", vault_start)
        pointer = result[vault_start:vault_end]

        vault = ArtifactVault(str(tmp_path))
        stored_bytes = vault.get(pointer)
        assert stored_bytes == content.encode("utf-8")
        assert len(stored_bytes) == len(content.encode("utf-8"))

    def test_handler_summary_quality(self, tmp_path: Path) -> None:
        """Verify summary preserves head and tail for useful context."""
        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))
        head_text = "SELECT id, name FROM users WHERE active = true LIMIT 100;\n"
        tail_text = "\nTotal rows: 50000 | Execution time: 1.23s"
        middle = "row_data_" * 10_000
        content = head_text + middle + tail_text

        result = handler(content, "mcp__db__run_query")

        assert result is not None
        assert head_text[:50] in result
        assert tail_text[-30:] in result
        assert "chars omitted" in result

    def test_handler_with_process_session_tools(self, tmp_path: Path) -> None:
        """Verify oversized_result_handler flows through process_session_tools."""
        from unittest.mock import MagicMock

        from langchain_core.tools import BaseTool

        from myrm_agent_harness.toolkits.mcp.agent import MCPAgent

        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))

        big_output = "Z" * 150_000

        async def big_fn(*args: object, **kwargs: object) -> str:
            return big_output

        tool = MagicMock(spec=BaseTool)
        tool.name = "big_tool"
        tool.description = "Returns large data"
        tool.coroutine = big_fn
        tool.metadata = {}

        processed = MCPAgent.process_session_tools(
            [tool],
            server_name="test_srv",
            tool_include=None,
            tool_exclude=None,
            execute_timeout=30.0,
            max_output_chars=100_000,
            oversized_result_handler=handler,
        )

        assert len(processed) == 1

    @pytest.mark.asyncio
    async def test_wrapped_tool_vaults_oversized_result(self, tmp_path: Path) -> None:
        """Full chain: process_session_tools → invoke → vault spill → verify stored."""
        from unittest.mock import MagicMock

        from langchain_core.tools import BaseTool

        from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
        from myrm_agent_harness.toolkits.mcp.agent import MCPAgent

        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))
        big_output = "VAULT_TEST_ROW_" * 10_000  # 150K chars

        async def big_fn(*args: object, **kwargs: object) -> str:
            return big_output

        tool = MagicMock(spec=BaseTool)
        tool.name = "data_export"
        tool.description = "Exports large dataset"
        tool.coroutine = big_fn
        tool.metadata = {}

        processed = MCPAgent.process_session_tools(
            [tool],
            server_name="db_srv",
            tool_include=None,
            tool_exclude=None,
            execute_timeout=30.0,
            max_output_chars=100_000,
            oversized_result_handler=handler,
        )

        result = await processed[0].coroutine()
        assert isinstance(result, str)
        assert "vault://" in result
        assert "file_read_tool" in result
        assert "VAULT_TEST_ROW_" in result

        from myrm_agent_harness.agent.artifacts.vault import VAULT_PREFIX

        vault = ArtifactVault(str(tmp_path))
        objects = vault.list_objects()
        assert len(objects) == 1
        pointer = f"{VAULT_PREFIX}{objects[0].id}"
        stored = vault.get(pointer)
        assert stored == big_output.encode("utf-8")


class TestVaultHandlerNegativePaths:
    """Integration tests for failure and edge-case paths."""

    @pytest.mark.asyncio
    async def test_no_handler_truncates_gracefully(self) -> None:
        """Without handler, oversized output is truncated (existing behavior)."""
        from unittest.mock import MagicMock

        from langchain_core.tools import BaseTool

        from myrm_agent_harness.toolkits.mcp.agent import MCPAgent

        big_output = "TRUNC_" * 30_000

        async def big_fn(*args: object, **kwargs: object) -> str:
            return big_output

        tool = MagicMock(spec=BaseTool)
        tool.name = "no_vault"
        tool.description = "No vault handler"
        tool.coroutine = big_fn
        tool.metadata = {}

        processed = MCPAgent.process_session_tools(
            [tool],
            server_name="plain_srv",
            tool_include=None,
            tool_exclude=None,
            execute_timeout=30.0,
            max_output_chars=100_000,
        )

        result = await processed[0].coroutine()
        assert isinstance(result, str)
        assert "[Output truncated" in result
        assert "vault://" not in result

    @pytest.mark.asyncio
    async def test_small_output_passes_through(self, tmp_path: Path) -> None:
        """Small output is not vaulted, just wrapped with content boundary."""
        from unittest.mock import MagicMock

        from langchain_core.tools import BaseTool

        from myrm_agent_harness.toolkits.mcp.agent import MCPAgent

        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))

        async def small_fn(*args: object, **kwargs: object) -> str:
            return "small result"

        tool = MagicMock(spec=BaseTool)
        tool.name = "small_tool"
        tool.description = "Returns small data"
        tool.coroutine = small_fn
        tool.metadata = {}

        processed = MCPAgent.process_session_tools(
            [tool],
            server_name="lite_srv",
            tool_include=None,
            tool_exclude=None,
            execute_timeout=30.0,
            max_output_chars=100_000,
            oversized_result_handler=handler,
        )

        result = await processed[0].coroutine()
        assert isinstance(result, str)
        assert "small result" in result
        assert "vault://" not in result
        assert "UNTRUSTED_DATA" in result
