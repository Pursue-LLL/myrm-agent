"""A text archive is stored byte-for-byte, so a retry of the same offload reuses it instead of rewriting it.

The reuse check compares the stored file with the size and hash computed from the text. A writer that translates
newlines (the default text mode on Windows) makes the file differ from that text, so every later store of the same
content found a mismatch and wrote the archive again. The tests emulate that translation on any host and run the real
``LocalExecutor`` write path.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from myrm_agent_harness.core.paths import PERSISTENT_ROOT_ENV
from myrm_agent_harness.runtime.context.archive_store import (
    ContentAddressedArchiveWrite,
    store_content_addressed_archive,
)
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from tests.support.windows_text_mode import emulate_windows_text_mode

_TEXTS = {
    "lf": "alpha\nbeta\ngamma\n",
    "crlf": "alpha\r\nbeta\r\ngamma\r\n",
}


@pytest.fixture
def executor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalExecutor:
    monkeypatch.setenv(PERSISTENT_ROOT_ENV, str(tmp_path))
    local = LocalExecutor(ExecutionConfig())
    local.bind_workspace(str(tmp_path))
    return local


async def _store(executor: LocalExecutor, text: str) -> ContentAddressedArchiveWrite:
    raw = text.encode("utf-8")
    return await store_content_addressed_archive(
        executor=executor,
        session_id="chat_text_fidelity",
        tool_name="bash",
        content_sha256=sha256(raw).hexdigest(),
        original_bytes=len(raw),
        stored_content=text,
        compressed=False,
    )


@pytest.mark.parametrize("text", _TEXTS.values(), ids=_TEXTS.keys())
async def test_archive_holds_the_utf8_bytes_of_the_text_and_a_retry_reuses_it(
    executor: LocalExecutor, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    emulate_windows_text_mode(monkeypatch)

    first = await _store(executor, text)
    second = await _store(executor, text)

    assert Path(first.abs_path).read_bytes() == text.encode("utf-8")
    assert first.stored_bytes == len(text.encode("utf-8"))
    assert first.reused is False
    assert second.reused is True
