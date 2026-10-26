"""Contract: middleware readers find the workspace in the context a real run builds.

A hand-built context passes any key a reader asks for. These tests take the context from the
production setup path, so a reader of a key the run never writes goes red.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoItem, TodoStore
from myrm_agent_harness.agent.meta_tools.progress.storage import (
    read_todos_sync_from_workspace,
    write_todos_sync_to_workspace,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    CompletionGuard,
    reset_completion_guard,
)
from myrm_agent_harness.agent.middlewares.progress_middleware import progress_middleware
from tests.support.run_context import real_run_context

_LOOP_GUARD = "myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware.get_loop_guard"


@pytest.mark.asyncio
async def test_todo_focus_reaches_the_model_request(tmp_path: Path) -> None:
    context = await real_run_context(tmp_path)
    write_todos_sync_to_workspace(
        str(tmp_path), TodoStore(goal="Weekly report", todos=[TodoItem(id="t1", content="collect the numbers")])
    )

    async def get_todos(workspace_root: str | None) -> TodoStore | None:
        return read_todos_sync_from_workspace(workspace_root) if workspace_root else None

    runtime = type("Runtime", (), {"context": context})()
    request = ModelRequest(model=AsyncMock(), messages=[HumanMessage(content="continue")], runtime=runtime)
    handler = AsyncMock(return_value=ModelResponse(result=[]))

    await progress_middleware(get_todos).awrap_model_call(request, handler)

    sent = handler.await_args.args[0].messages[-1]
    assert "collect the numbers" in str(sent.content)


@pytest.mark.asyncio
async def test_completion_guard_stages_unwritten_deliverables_in_the_run_workspace(tmp_path: Path) -> None:
    context = await real_run_context(tmp_path)
    draft = (
        "```python\n"
        "# filename: draft_worker.py\n"
        "import time\n"
        "\n"
        "def run_worker():\n"
        "    print('working')\n"
        "    time.sleep(1)\n"
        "```"
    )
    state = {"messages": [HumanMessage(content="写一个 worker 脚本"), AIMessage(content=f"完成：\n{draft}")]}
    runtime = {"configurable": {"context": context}}
    guard = CompletionGuard(max_rejections=1)
    reset_completion_guard()

    with patch(_LOOP_GUARD) as loop_guard:
        loop_guard.return_value = MagicMock(_window=[])
        await guard.aafter_model(state, runtime)
        forced = await guard.aafter_model(state, runtime)

    args = forced["messages"][0].tool_calls[0]["args"]
    assert args["force_fail"] is True
    assert args["workspace_root"] == str(tmp_path)
    assert list((tmp_path / ".myrm" / "staged_artifacts").glob("*draft_worker.py"))
