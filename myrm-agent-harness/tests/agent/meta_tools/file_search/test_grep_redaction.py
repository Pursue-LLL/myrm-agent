"""grep redacts each match by the type of its file, so the same line reads the same in grep as in file_read_tool."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_search._redaction import Match, redact_matches
from myrm_agent_harness.agent.meta_tools.file_search.grep_tool import create_grep_tool
from myrm_agent_harness.core.security.redact import redact_sensitive_text

_PRIVATE_KEY = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7\n"
    "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQR\n"
    "-----END PRIVATE KEY-----"
)


# Lines of code that full-mode redaction rewrites, because a type name and a variable name contain ``token``.
_TOKEN_NAMED_CODE = ("cancel_token: CancellationToken | None = None,", "saved_tokens: int")


def test_the_code_lines_used_below_are_rewritten_by_full_mode_redaction() -> None:
    assert all(redact_sensitive_text(line) != line for line in _TOKEN_NAMED_CODE)


def _match(file: str, line: int, content: str, kind: str = "match") -> Match:
    return {"file": file, "line": line, "content": content, "type": kind}


class TestRedactMatches:
    @pytest.mark.parametrize("line", _TOKEN_NAMED_CODE)
    def test_a_source_line_keeps_its_credential_named_identifiers(self, line: str) -> None:
        assert redact_matches([_match("a.py", 3, line)]) == [_match("a.py", 3, line)]

    def test_a_config_line_is_redacted_in_full(self) -> None:
        out = redact_matches([_match("app.env", 1, "DB_PASSWORD=hunter2"), _match("a.yaml", 2, "api_key: hunter2abc")])
        assert all("hunter2" not in str(m["content"]) for m in out)

    def test_each_file_is_redacted_by_its_own_type(self) -> None:
        line = "total_api_tokens = 0"
        out = redact_matches([_match("a.py", 1, line), _match("a.env", 1, line)])
        assert out[0]["content"] == line
        assert out[1]["content"] == "total_api_tokens=***"

    def test_a_literal_secret_in_source_is_still_masked(self) -> None:
        out = redact_matches([_match("a.py", 1, 'API_KEY = "sk-abc123def456ghi789jkl"')])
        assert "sk-abc123def456ghi789jkl" not in str(out[0]["content"])

    def test_other_fields_of_a_match_survive(self) -> None:
        (out,) = redact_matches([_match("a.py", 7, "x = 1", kind="context")])
        assert out == _match("a.py", 7, "x = 1", kind="context")

    def test_a_pem_block_across_consecutive_lines_is_masked(self) -> None:
        matches = [_match("key.pem", n, line) for n, line in enumerate(_PRIVATE_KEY.split("\n"), 1)]
        out = redact_matches(matches)
        body = "\n".join(str(m["content"]) for m in out)
        assert "MIIEvQIBADANBg" not in body
        assert "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQR" not in body
        assert [m["line"] for m in out] == [1, 2, 3, 4]

    def test_lines_of_different_files_or_gaps_are_redacted_apart(self) -> None:
        matches = [_match("a.py", 1, "x = 1"), _match("a.py", 9, "y = 2"), _match("b.py", 10, "z = 3")]
        assert redact_matches(matches) == matches

    def test_a_run_redacted_to_fewer_lines_is_padded_never_split_per_line(self) -> None:
        matches = [_match("a.env", n, f"line {n}") for n in (1, 2, 3)]
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search._redaction.redact_file_text",
            return_value="head\nblock",
        ):
            assert [m["content"] for m in redact_matches(matches)] == ["head", "block", ""]

    def test_a_run_redacted_to_more_lines_is_joined_into_its_last_line(self) -> None:
        matches = [_match("a.env", n, f"line {n}") for n in (1, 2)]
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search._redaction.redact_file_text",
            return_value="a\nb\nc",
        ):
            assert [m["content"] for m in redact_matches(matches)] == ["a", "b c"]

    def test_no_matches(self) -> None:
        assert redact_matches([]) == []


@pytest.mark.asyncio
class TestGrepToolOutput:
    @pytest.fixture
    def executor(self, tmp_path: Path) -> AsyncMock:
        executor = AsyncMock()

        async def resolve_path(p: str) -> str:
            return str(tmp_path) if p == "." else str(tmp_path / p)

        executor.resolve_path = resolve_path
        return executor

    async def _grep(self, executor: AsyncMock, **args: str | bool | int) -> str:
        tool = create_grep_tool()
        with patch(
            "myrm_agent_harness.agent.meta_tools.file_search.grep_tool.ensure_executor",
            return_value=executor,
        ):
            return str(await tool.ainvoke(args, config=RunnableConfig(configurable={})))

    async def test_source_lines_read_as_written(self, tmp_path: Path, executor: AsyncMock) -> None:
        (tmp_path / "svc.py").write_text("\n".join(_TOKEN_NAMED_CODE) + "\n")
        out = await self._grep(executor, pattern="token")
        assert all(line in out for line in _TOKEN_NAMED_CODE)

    async def test_a_config_file_is_still_redacted_in_full(self, tmp_path: Path, executor: AsyncMock) -> None:
        (tmp_path / "prod.env").write_text("DB_PASSWORD=hunter2\n")
        out = await self._grep(executor, pattern="DB_PASSWORD")
        assert "hunter2" not in out
        assert "DB_PASSWORD=***" in out

    async def test_a_secret_searched_for_is_not_echoed(self, tmp_path: Path, executor: AsyncMock) -> None:
        (tmp_path / "a.txt").write_text("nothing here\n")
        secret = "sk-abc123def456ghi789jkl012"
        out = await self._grep(executor, pattern=secret, literal=True)
        assert secret not in out
        assert "No matches found" in out

    async def test_context_lines_are_redacted_like_matches(self, tmp_path: Path, executor: AsyncMock) -> None:
        (tmp_path / "a.py").write_text('# marker\nAPI_KEY = "sk-abc123def456ghi789jkl012"\n')
        out = await self._grep(executor, pattern="marker", context_lines=1)
        assert "API_KEY" in out
        assert "sk-abc123def456ghi789jkl012" not in out
