"""LocalExecutor.grep without ripgrep: valid GNU/BSD flags and shell-safe quoting."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor

pytestmark = pytest.mark.asyncio


@dataclass
class _Shell:
    stdout: str = ""
    success: bool = True


@pytest.fixture(autouse=True)
def _disable_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    from myrm_agent_harness.toolkits.code_execution.sandbox.providers.null import NullProvider
    from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxStatus

    null_result = (NullProvider(), SandboxStatus(enabled=False, provider_name="null", reason="test"))

    def fake(**_kwargs: object) -> tuple[NullProvider, SandboxStatus]:
        return null_result

    monkeypatch.setattr("myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider", fake)
    monkeypatch.setattr("myrm_agent_harness.toolkits.code_execution.sandbox.detector.detect_sandbox_provider", fake)


@pytest.fixture
def executor(tmp_path: Path) -> Iterator[LocalExecutor]:
    (tmp_path / "a.py").write_text("def hello_world():\n    pass\nIMPORT = 1\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("import os\n-v flag\n", encoding="utf-8")
    instance = LocalExecutor(ExecutionConfig(workspace_path=str(tmp_path)), str(tmp_path))
    instance._has_ripgrep = False
    yield instance


@pytest.mark.parametrize(
    ("use_regex", "case_sensitive", "flags"),
    [
        (False, True, "-rnF"),
        (True, True, "-rnE"),
        (False, False, "-rnFi"),
        (True, False, "-rnEi"),
    ],
)
async def test_fallback_builds_single_dash_flag_cluster(
    executor: LocalExecutor, use_regex: bool, case_sensitive: bool, flags: str
) -> None:
    commands: list[str] = []

    async def spy(command: str) -> _Shell:
        commands.append(command)
        return _Shell()

    executor._exec_bash = spy  # type: ignore[method-assign]
    await executor.grep("needle", use_regex=use_regex, case_sensitive=case_sensitive)

    assert commands[0].startswith(f"grep {flags} -- needle ")


async def test_quote_in_pattern_cannot_break_out_of_the_command(executor: LocalExecutor) -> None:
    commands: list[str] = []

    async def spy(command: str) -> _Shell:
        commands.append(command)
        return _Shell()

    executor._exec_bash = spy  # type: ignore[method-assign]
    await executor.grep("x'; touch pwned; echo '")

    assert commands[0].startswith("grep -rnF -- 'x'\"'\"'; touch pwned; echo '\"'\"'' ")


@pytest.mark.skipif(shutil.which("rg") is not None, reason="hosts with ripgrep never take the grep fallback")
class TestRealGrepBinary:
    async def test_literal_regex_and_case_insensitive_search(self, executor: LocalExecutor) -> None:
        assert "hello_world" in await executor.grep("hello_world")
        regex_result = await executor.grep(r"^import |def \w+\(", use_regex=True)
        assert "import os" in regex_result
        assert "def hello_world" in regex_result
        assert "IMPORT = 1" in await executor.grep("import", case_sensitive=False)

    async def test_pattern_starting_with_dash_is_not_an_option(self, executor: LocalExecutor) -> None:
        assert "-v flag" in await executor.grep("-v flag")
