"""Tests for the ACP callback handler's session updates, file operations and helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.toolkits.acp.runtime.acp_callback import AcpCallbackHandler
from myrm_agent_harness.toolkits.acp.types import PermissionDecision, RuntimeConfig


class TestAcpCallbackHandlerSessionUpdate:
    @pytest.mark.asyncio
    async def test_agent_message_chunk_text(self) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy"),
            "s1",
        )
        update = MagicMock()
        update.session_update = "agent_message_chunk"
        update.sessionUpdate = None
        update.content = MagicMock()
        update.content.type = "text"
        update.content.text = "hello world"
        await handler.session_update("s1", update)
        assert "hello world" in handler.response_text

    @pytest.mark.asyncio
    async def test_tool_call_update(self) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy"),
            "s1",
        )
        update = MagicMock()
        update.session_update = "tool_call"
        update.sessionUpdate = None
        update.title = "bash"
        update.status = "running"
        update.content = None
        await handler.session_update("s1", update)
        assert "bash" in handler.response_text

    @pytest.mark.asyncio
    async def test_tool_call_update_completed(self) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy"),
            "s1",
        )
        update = MagicMock()
        update.session_update = "tool_call_update"
        update.sessionUpdate = None
        update.status = "completed"
        update.tool_call_id = "tc1"
        update.toolCallId = None
        update.content = None
        await handler.session_update("s1", update)
        assert "tc1" in handler.response_text

    @pytest.mark.asyncio
    async def test_agent_thought_chunk(self) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy"),
            "s1",
        )
        update = MagicMock()
        update.session_update = "agent_thought_chunk"
        update.sessionUpdate = None
        update.content = MagicMock()
        update.content.type = "text"
        update.content.text = "thinking..."
        await handler.session_update("s1", update)
        assert "thinking..." in handler.response_text

    @pytest.mark.asyncio
    async def test_reset_clears_text(self) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy"),
            "s1",
        )
        handler._text_parts.append("old text")
        handler.reset()
        assert handler.response_text == ""


class TestAcpCallbackHandlerFileOps:
    @pytest.mark.asyncio
    async def test_read_text_file_within_cwd(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("file content", encoding="utf-8")
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy", cwd=str(tmp_path)),
            "s1",
        )
        result = await handler.read_text_file(str(test_file), "s1")
        assert result["content"] == "file content"

    @pytest.mark.asyncio
    async def test_read_text_file_with_line_range(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy", cwd=str(tmp_path)),
            "s1",
        )
        result = await handler.read_text_file(str(test_file), "s1", limit=1, line=2)
        assert "line2" in result["content"]

    @pytest.mark.asyncio
    async def test_read_text_file_outside_cwd(self, tmp_path: Path) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy", cwd=str(tmp_path / "sub")),
            "s1",
        )
        result = await handler.read_text_file("/etc/passwd", "s1")
        assert "[error]" in result["content"]

    @pytest.mark.asyncio
    async def test_read_text_file_nonexistent(self, tmp_path: Path) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(backend_type="acp", command="dummy", cwd=str(tmp_path)),
            "s1",
        )
        result = await handler.read_text_file(str(tmp_path / "nope.txt"), "s1")
        assert "[error]" in result["content"]

    @pytest.mark.asyncio
    async def test_write_text_file_allow_all(self, tmp_path: Path) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(
                backend_type="acp",
                command="dummy",
                cwd=str(tmp_path),
                permission_mode="allow_all",
            ),
            "s1",
        )
        target = tmp_path / "output.txt"
        result = await handler.write_text_file("content", str(target), "s1")
        assert result == {"success": True}
        assert target.read_text() == "content"

    @pytest.mark.asyncio
    async def test_write_text_file_safe_mode_denied(self, tmp_path: Path) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(
                backend_type="acp",
                command="dummy",
                cwd=str(tmp_path),
                permission_mode="safe",
            ),
            "s1",
        )
        result = await handler.write_text_file("content", str(tmp_path / "out.txt"), "s1")
        assert result is None

    @pytest.mark.asyncio
    async def test_write_text_file_outside_cwd(self, tmp_path: Path) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(
                backend_type="acp",
                command="dummy",
                cwd=str(tmp_path),
                permission_mode="allow_all",
            ),
            "s1",
        )
        result = await handler.write_text_file("content", "/tmp/evil.txt", "s1")
        assert result is None

    @pytest.mark.asyncio
    async def test_write_text_file_parent_mkdir_failure(self, tmp_path: Path) -> None:
        handler = AcpCallbackHandler(
            RuntimeConfig(
                backend_type="acp",
                command="dummy",
                cwd=str(tmp_path),
                permission_mode="allow_all",
            ),
            "s1",
        )
        # A path whose parent is an existing file forces mkdir → FileExistsError/OSError.
        blocker = tmp_path / "blocker"
        blocker.write_text("i am a file")
        target = blocker / "sub" / "out.txt"
        result = await handler.write_text_file("content", str(target), "s1")
        assert result is None


class TestAcpCallbackHelpers:
    """Pure helper boundaries: text extraction, safe-path resolution, option lookup."""

    def test_extract_text_content_none(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime import acp_callback as mod

        assert mod._extract_text_content(None) is None

    def test_extract_text_content_non_text_type(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime import acp_callback as mod

        class _Other:
            type = "image"

        assert mod._extract_text_content(_Other()) is None

    def test_extract_text_content_text_no_text_field(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime import acp_callback as mod

        class _Text:
            type = "text"

        assert mod._extract_text_content(_Text()) is None

    def test_resolve_safe_path_inside_cwd(self, tmp_path: Path) -> None:
        from myrm_agent_harness.toolkits.acp.runtime import acp_callback as mod

        resolved = mod._resolve_safe_path("sub/file.txt", str(tmp_path))
        assert resolved is not None
        assert str(resolved).startswith(str(tmp_path))

    def test_resolve_safe_path_escape_returns_none(self, tmp_path: Path) -> None:
        from myrm_agent_harness.toolkits.acp.runtime import acp_callback as mod

        assert mod._resolve_safe_path("../evil.txt", str(tmp_path)) is None
        assert mod._resolve_safe_path("/etc/passwd", str(tmp_path)) is None

    def test_resolve_safe_path_oserror_returns_none(self, tmp_path: Path, monkeypatch) -> None:
        from myrm_agent_harness.toolkits.acp.runtime import acp_callback as mod

        class _BoomPath(Path):
            def resolve(self, strict: bool = False) -> Path:
                raise OSError("too many symlinks")

        with monkeypatch.context() as m:
            # Force Path(...) inside _resolve_safe_path to hit OSError via resolve.
            m.setattr("myrm_agent_harness.toolkits.acp.runtime.acp_callback.Path", _BoomPath)
            assert mod._resolve_safe_path("file.txt", str(tmp_path)) is None

    def test_find_option_non_dict_option(self) -> None:
        from myrm_agent_harness.toolkits.acp.runtime import acp_callback as mod

        assert mod._find_option([object()], ("allow_once",)) is None
        assert mod._find_option([], ("allow_once",)) is None

    def test_decision_to_option_allow_always(self) -> None:
        options = [
            {"kind": "allow_once", "optionId": "allow_once"},
            {"kind": "allow_always", "optionId": "allow_always"},
            {"kind": "reject_once", "optionId": "reject_once"},
            {"kind": "reject_always", "optionId": "reject_always"},
        ]
        # _find_option returns the first option whose kind is in the decision's
        # accepted set, in list order (ACP does not guarantee option ordering).
        assert AcpCallbackHandler._decision_to_option(options, PermissionDecision.ALLOW_ALWAYS) == "allow_once"
        assert AcpCallbackHandler._decision_to_option(options, PermissionDecision.DENY_ALWAYS) == "reject_once"

    def test_decision_to_option_prefers_primary_kind(self) -> None:
        # allow_always listed first → the primary kind wins.
        options = [
            {"kind": "allow_always", "optionId": "allow_always"},
            {"kind": "allow_once", "optionId": "allow_once"},
        ]
        assert AcpCallbackHandler._decision_to_option(options, PermissionDecision.ALLOW_ALWAYS) == "allow_always"

    def test_decision_to_option_unmappable_returns_none(self) -> None:
        # Decision wants allow_always but only reject options exist → None (invalid).
        options = [{"kind": "reject_once", "optionId": "reject_once"}]
        assert AcpCallbackHandler._decision_to_option(options, PermissionDecision.ALLOW_ALWAYS) is None
