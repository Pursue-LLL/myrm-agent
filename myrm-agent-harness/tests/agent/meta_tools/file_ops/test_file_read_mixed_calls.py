"""A text path reads the same whether or not the call also reads a document: same pages, mode and redaction.

A call that reads a notebook (or any Word, Excel, slide file) is answered in content blocks; a call of text paths only
is answered in one string. Both read their text paths through the same pipeline, and the text of every block a document
reader returns is redacted as that document's file type is. Runs the real chain: ``file_read_tool`` through a
``LocalExecutor`` on real files.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.config import DEFAULT_FILE_IO_CONFIG
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor

# Names that read as credentials but hold plain numbers, and one real literal secret.
_CONFIG = 'max_tokens = 4096\nAPI_TIMEOUT_TOKENS = 30\nDEFAULT_PASSWORD = "Xk9$mP2vLq8"\n'
_SERVICE = "class Service:\n    def start(self):\n        return 1\n\n\ndef helper():\n    return 3\n"
_NOTEBOOK = {
    "cells": [
        {
            "cell_type": "code",
            "metadata": {},
            "execution_count": None,
            "outputs": [],
            "source": ["max_tokens = 4096\n", 'DEFAULT_PASSWORD = "Xk9$mP2vLq8"\n', "print(max_tokens)\n"],
        },
        {"cell_type": "markdown", "metadata": {}, "source": ["Use sk-abcdefghijklmnop1234567890 for the demo.\n"]},
    ],
    "metadata": {},
    "nbformat": 4,
    "nbformat_minor": 5,
}


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path.resolve()
    (root / "cfg.py").write_text(_CONFIG, encoding="utf-8")
    (root / "mod.py").write_text(_SERVICE, encoding="utf-8")
    (root / "big.txt").write_text("".join(f"line {n:05d} {'x' * 40}\n" for n in range(1, 12_001)), encoding="utf-8")
    (root / "nb.ipynb").write_text(json.dumps(_NOTEBOOK), encoding="utf-8")
    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(root)))
    root_token = workspace_root_var.set(str(root))
    try:
        yield root
    finally:
        workspace_root_var.reset(root_token)
        reset_executor(executor_token)


async def _read(args: dict[str, object]) -> list[str]:
    """The text of the answer, one entry per text block (a plain answer is one entry)."""
    answer = await create_file_read_tool().ainvoke(args, config=RunnableConfig())
    if isinstance(answer, str):
        return [answer]
    assert isinstance(answer, list)
    return [str(block["text"]) for block in answer if isinstance(block, dict) and block.get("type") == "text"]


def _same_text(text: str) -> str:
    """The text with the random id of its tool-output tags blanked, so two reads of one file compare equal."""
    return re.sub(r'id="[0-9a-f]+"', 'id="-"', text)


class TestATextPathNextToADocument:
    @pytest.mark.parametrize(
        ("paths", "extra"),
        [
            (["cfg.py"], {}),
            (["cfg.py:1-2"], {}),
            (["mod.py"], {"parse_mode": "structure"}),
            (["big.txt"], {}),
            (["big.txt"], {"mode": "preview"}),
            (["big.txt"], {"mode": "stream"}),
        ],
        ids=["source", "ranged", "structure", "page-cap", "preview", "stream"],
    )
    async def test_it_reads_as_it_does_alone(self, workspace: Path, paths: list[str], extra: dict[str, object]) -> None:
        alone = await _read({"paths": paths, **extra})
        beside_a_notebook = await _read({"paths": [*paths, "nb.ipynb"], **extra})

        assert len(alone) == 1
        assert _same_text(beside_a_notebook[-1]) == _same_text(alone[0])

    async def test_code_that_only_names_credentials_stays_readable_and_a_literal_secret_does_not(
        self, workspace: Path
    ) -> None:
        text = (await _read({"paths": ["cfg.py", "nb.ipynb"]}))[-1]

        assert "max_tokens = 4096" in text
        assert "API_TIMEOUT_TOKENS = 30" in text
        assert "Xk9$mP2vLq8" not in text

    async def test_a_long_file_is_paged_not_dumped_whole(self, workspace: Path) -> None:
        text = (await _read({"paths": ["big.txt", "nb.ipynb"]}))[-1]

        assert len(text) < 2 * DEFAULT_FILE_IO_CONFIG.max_read_chars
        assert "line 12000" not in text


class TestTheTextOfADocument:
    async def test_a_notebook_is_redacted_as_source_code(self, workspace: Path) -> None:
        text = "\n".join(await _read({"paths": ["nb.ipynb"]}))

        assert "max_tokens = 4096" in text
        assert "Xk9$mP2vLq8" not in text
        assert "sk-abcdefghijklmnop1234567890" not in text

    async def test_a_url_refusal_does_not_repeat_the_secret_in_the_url(self, workspace: Path) -> None:
        answer = "\n".join(
            await _read({"paths": ["https://a.example/x?api_key=sk-secretvalue1234567890abcdef", "nb.ipynb"]})
        )

        assert "cannot read URLs" in answer
        assert "sk-secretvalue1234567890abcdef" not in answer
