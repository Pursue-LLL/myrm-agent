"""``file_read_tool`` reads local files only: the URLs in a call are refused by name and the rest is read."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read.scope import partition_urls
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor


def test_a_call_without_urls_is_left_alone() -> None:
    local, refusal = partition_urls(["a.py", "src/b.py:3-9", "vault://0a1b2c", "/mcp/gmail/send.md"])

    assert local == ["a.py", "src/b.py:3-9", "vault://0a1b2c", "/mcp/gmail/send.md"]
    assert refusal == ""


@pytest.mark.parametrize(
    "url",
    ["http://a.example/x", "https://a.example/x", "ftp://a.example/x", "FTPS://a.example/x", "HtTpS://a.example/x"],
)
def test_every_network_scheme_is_refused_whatever_its_case(url: str) -> None:
    local, refusal = partition_urls(["a.py", url])

    assert local == ["a.py"]
    assert url in refusal
    assert "cannot read URLs" in refusal
    assert "local file paths" in refusal


@pytest.mark.parametrize("path", ["notes/http://x", "file:///tmp/a.txt", "C:/data/a.csv", "httpd.conf", "https.md"])
def test_a_local_path_that_only_mentions_a_scheme_is_not_a_url(path: str) -> None:
    local, refusal = partition_urls([path])

    assert local == [path]
    assert refusal == ""


def test_the_refusal_names_the_first_three_urls_and_counts_the_rest() -> None:
    urls = [f"https://a.example/{n}" for n in range(5)]

    local, refusal = partition_urls(["a.py", *urls])

    assert local == ["a.py"]
    assert all(url in refusal for url in urls[:3])
    assert not any(url in refusal for url in urls[3:])
    assert "(and 2 more)" in refusal


def test_three_urls_are_all_named_without_a_count() -> None:
    urls = [f"https://a.example/{n}" for n in range(3)]

    _, refusal = partition_urls(urls)

    assert all(url in refusal for url in urls)
    assert "more)" not in refusal


def test_a_call_made_only_of_urls_leaves_nothing_to_read() -> None:
    local, refusal = partition_urls(["https://a.example/x"])

    assert local == []
    assert refusal


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path.resolve()
    (root / "a.py").write_text("LOCAL-CONTENT\n", encoding="utf-8")
    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(root)))
    workspace_token = workspace_root_var.set(str(root))
    yield root
    workspace_root_var.reset(workspace_token)
    reset_executor(executor_token)


async def _read(paths: list[str]) -> str:
    return str(await create_file_read_tool().ainvoke({"paths": paths, "mode": "all"}, config=RunnableConfig()))


@pytest.mark.asyncio
@pytest.mark.integration
async def test_the_local_file_is_read_and_the_url_is_refused_in_the_same_answer(workspace: Path) -> None:
    answer = await _read(["https://a.example/x", "a.py"])

    assert "LOCAL-CONTENT" in answer
    assert "cannot read URLs: https://a.example/x" in answer
    assert answer.index("cannot read URLs") < answer.index("LOCAL-CONTENT")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_a_call_made_only_of_urls_answers_with_the_refusal(workspace: Path) -> None:
    answer = await _read(["https://a.example/x", "ftp://b.example/y"])

    assert answer.startswith("file_read_tool cannot read URLs: https://a.example/x, ftp://b.example/y")
