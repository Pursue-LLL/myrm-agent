"""The path a background job's log is reported under, as the model is shown it.

The guardrail masks random-looking tokens in a tool result. The id of an external-transcript chat reads as one, and it
stands in the log path and, as a value of its own, in the result's metadata. The path must reach the model whole: the
model opens the log by it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.bash._background.registry import get_background_registry
from myrm_agent_harness.agent.meta_tools.bash._background.types import OUTPUT_RING_LINES
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import create_bash_process_tool
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.fake_background_proc import FakeProc, wait_until
from tests.agent.meta_tools.bash.guardrail_view import shown_to_model

pytestmark = pytest.mark.usefixtures("jobs")

# The shape of an external-transcript chat id (ext_<source>_<path hash>): a random token to the guardrail.
_CHAT = "ext_cursor_7f3a9c2e1b4d6f80"


@pytest.mark.asyncio
async def test_the_log_path_is_shown_whole_in_a_chat_whose_id_reads_as_a_secret(
    jobs: list[FakeProc], workspace: Path
) -> None:
    pid = 74001
    printed = [f"line-{i}" for i in range(OUTPUT_RING_LINES + 50)]
    proc = FakeProc(pid=pid, stdout=[("\n".join(printed) + "\n").encode()], stderr=[])
    jobs.append(proc)
    registry = get_background_registry()
    await registry.register(cast(AsyncProcessProtocol, proc), command="generate", session_id=_CHAT)
    proc.finish(0)
    await wait_until(
        lambda: (info := registry.get(pid)) is not None and info.status != "running", what="the job to settle"
    )
    config: RunnableConfig = {"configurable": {"context": {"session_id": _CHAT}}}

    result = await create_bash_process_tool().ainvoke({"action": "output", "pid": pid}, config=config)
    shown = json.loads(shown_to_model(result))

    log_file = result["content"]["log_file"]
    assert (workspace / log_file).is_file()
    assert shown["content"]["log_file"] == log_file
