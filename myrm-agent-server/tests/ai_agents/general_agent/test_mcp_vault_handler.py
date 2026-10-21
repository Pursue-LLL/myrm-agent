"""Tests for mcp_vault_handler.build_mcp_vault_handler.

Covers:
- Successful vault spill with vault:// pointer and summary
- Vault write failure returns None (fallback to truncation)
- push_inline_artifact failure is non-fatal
- Summary head/tail composition
- Handler closure captures workspace_root correctly
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch


class TestBuildMcpVaultHandler:
    """Test build_mcp_vault_handler factory and returned closure."""

    def test_handler_returns_summary_with_vault_pointer(self, tmp_path: Path) -> None:
        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))
        content = "A" * 5_000
        result = handler(content, "test_tool")

        assert result is not None
        assert "vault://" in result
        assert "file_read_tool" in result
        assert "Full result stored in vault" in result

    def test_handler_summary_contains_head(self, tmp_path: Path) -> None:
        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))
        content = "HEAD_MARKER_" + "x" * 10_000
        result = handler(content, "head_tool")

        assert result is not None
        assert "HEAD_MARKER_" in result

    def test_handler_summary_contains_tail_for_large_content(self, tmp_path: Path) -> None:
        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))
        content = "x" * 10_000 + "TAIL_MARKER"
        result = handler(content, "tail_tool")

        assert result is not None
        assert "TAIL_MARKER" in result

    def test_handler_summary_omits_middle_for_large_content(self, tmp_path: Path) -> None:
        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))
        content = "H" * 2_000 + "M" * 10_000 + "T" * 1_000
        result = handler(content, "mid_tool")

        assert result is not None
        assert "chars omitted" in result

    def test_handler_no_omission_for_small_content(self, tmp_path: Path) -> None:
        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))
        content = "small"
        result = handler(content, "small_tool")

        assert result is not None
        assert "chars omitted" not in result
        assert "small" in result

    def test_handler_vault_write_failure_returns_none(self) -> None:
        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler("/nonexistent/path/that/should/fail")

        with patch(
            "myrm_agent_harness.agent.artifacts.vault.ArtifactVault.put",
            side_effect=RuntimeError("disk full"),
        ):
            result = handler("content", "fail_tool")

        assert result is None

    def test_handler_artifact_push_failure_non_fatal(self, tmp_path: Path) -> None:
        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))

        with patch(
            "myrm_agent_harness.agent.artifacts.registry.push_inline_artifact",
            side_effect=RuntimeError("SSE broken"),
        ):
            result = handler("content data", "push_fail_tool")

        assert result is not None
        assert "vault://" in result

    def test_handler_filename_sanitizes_colons(self, tmp_path: Path) -> None:
        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))
        result = handler("data", "mcp__server__tool:v2")

        assert result is not None
        assert "vault://" in result

    def test_handler_stores_full_content_in_vault(self, tmp_path: Path) -> None:
        from myrm_agent_harness.agent.artifacts.vault import VAULT_PREFIX, ArtifactVault

        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        handler = build_mcp_vault_handler(str(tmp_path))
        original_content = "FULL_CONTENT_" * 1_000
        result = handler(original_content, "store_tool")

        assert result is not None
        pointer_start = result.index(VAULT_PREFIX)
        pointer_end = result.index("]", pointer_start)
        pointer = result[pointer_start:pointer_end]

        vault = ArtifactVault(str(tmp_path))
        stored = vault.get(pointer)
        assert stored == original_content.encode("utf-8")

    def test_handler_closure_captures_workspace(self) -> None:
        from app.ai_agents.general_agent.mcp_vault_handler import build_mcp_vault_handler

        with tempfile.TemporaryDirectory() as tmpdir:
            handler = build_mcp_vault_handler(tmpdir)
            result = handler("test", "closure_tool")
            assert result is not None
            assert "vault://" in result


class TestMcpVaultHandlerIntegrationWithConfig:
    """Test that MCPServerConfig accepts oversized_result_handler."""

    def test_mcp_server_config_accepts_handler(self) -> None:
        from app.core.types.business import MCPServerConfig

        def dummy_handler(c: str, t: str) -> str | None:
            return None

        cfg = MCPServerConfig(
            name="test",
            type="stdio",
            command="echo",
            oversized_result_handler=dummy_handler,
        )
        assert cfg.oversized_result_handler is dummy_handler

    def test_handler_excluded_from_serialization(self) -> None:
        from app.core.types.business import MCPServerConfig

        cfg = MCPServerConfig(
            name="test",
            type="stdio",
            command="echo",
            oversized_result_handler=lambda c, t: None,
        )
        data = cfg.model_dump()
        assert "oversized_result_handler" not in data

    def test_model_copy_with_handler(self) -> None:
        from app.core.types.business import MCPServerConfig

        cfg = MCPServerConfig(name="test", type="stdio", command="echo")
        assert cfg.oversized_result_handler is None

        handler = lambda c, t: "vaulted"  # noqa: E731
        updated = cfg.model_copy(update={"oversized_result_handler": handler})
        assert updated.oversized_result_handler is handler
        assert cfg.oversized_result_handler is None
