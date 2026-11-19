"""``CodeExecutorMiddleware`` forwards every operation of the executor it wraps.

An operation the middleware does not forward falls back to the base-class default of ``CodeExecutor``: file
operations run as shell commands instead of the wrapped executor's own implementation, and a background process
is refused. A policy subclass then polices a path the wrapped executor never takes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor
from myrm_agent_harness.toolkits.code_execution.executors.middleware import CodeExecutorMiddleware
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext, ExecutionResult

_CONTEXT = ExecutionContext(code="echo hi", work_dir="/tmp")

# Every awaitable operation of ``CodeExecutor`` with the arguments it is called with.
_CALLS: dict[str, tuple[object, ...]] = {
    "execute": (_CONTEXT,),
    "execute_bash": (_CONTEXT,),
    "spawn_background_process": (_CONTEXT,),
    "read_file": ("a.txt",),
    "read_file_bytes": ("a.txt",),
    "write_file": ("a.txt", "text"),
    "write_file_bytes": ("a.txt", b"bytes"),
    "write_file_atomic": ("a.txt", "text"),
    "write_file_bytes_atomic": ("a.txt", b"bytes"),
    "delete_file": ("a.txt",),
    "file_exists": ("a.txt",),
    "is_dir": ("a.txt",),
    "file_size": ("a.txt",),
    "list_files": (".", "*"),
    "resolve_path": ("a.txt",),
    "close": (),
}
# The operations that give the caller the wrapped executor's answer; the others return nothing.
_ANSWERING = frozenset(
    {
        "execute",
        "execute_bash",
        "spawn_background_process",
        "read_file",
        "read_file_bytes",
        "file_exists",
        "is_dir",
        "file_size",
        "list_files",
        "resolve_path",
    }
)
_STATE = frozenset({"workspace_path", "bind_workspace", "get_executor_name", "metrics", "warm_up"})
_ANSWER = object()


class _Executor(CodeExecutor):
    """A real executor: the counters it accumulates are the object under test, not a mock's attribute."""

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        return ExecutionResult(success=True)

    async def execute_bash(self, context: ExecutionContext) -> ExecutionResult:
        return ExecutionResult(success=True)


def _wrapped_executor() -> AsyncMock:
    inner = AsyncMock(spec=CodeExecutor)
    inner.config = None
    return inner


def test_every_public_operation_of_the_executor_has_a_forwarding_case() -> None:
    """A public member added to ``CodeExecutor`` fails here until the middleware forwards it and a case lists it."""
    public = {
        name
        for name, member in vars(CodeExecutor).items()
        if not name.startswith("_") and (callable(member) or isinstance(member, property))
    }

    assert public == set(_CALLS) | _STATE


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", sorted(_CALLS))
async def test_the_call_reaches_the_wrapped_executor(operation: str) -> None:
    inner = _wrapped_executor()
    handled = getattr(inner, operation)
    handled.return_value = _ANSWER
    middleware = CodeExecutorMiddleware(inner)

    answer = await getattr(middleware, operation)(*_CALLS[operation])

    handled.assert_awaited_once_with(*_CALLS[operation])
    assert (answer is _ANSWER) == (operation in _ANSWERING)


def test_the_state_is_the_wrapped_executors() -> None:
    inner = _wrapped_executor()
    inner.workspace_path = "/work"
    inner.get_executor_name.return_value = "Inner"
    middleware = CodeExecutorMiddleware(inner)

    assert middleware.workspace_path == "/work"
    assert middleware.get_executor_name() == "Inner"
    assert middleware.metrics is inner.metrics

    middleware.bind_workspace("/other")
    inner.bind_workspace.assert_called_once_with("/other")

    middleware.warm_up()
    inner.warm_up.assert_called_once_with()


def test_wrapping_an_executor_keeps_the_counters_it_has_accumulated() -> None:
    """The skill-review pre-screener reads these counters from the executor a shadow run wrapped."""
    inner = _Executor()
    inner.metrics.record(ExecutionResult(success=True), "bash")
    inner.metrics.record(ExecutionResult(success=False, error_category="timeout"), "python")

    middleware = CodeExecutorMiddleware(inner)

    assert middleware.metrics is inner.metrics
    assert (inner.metrics.total_executions, inner.metrics.total_success, inner.metrics.total_failures) == (2, 1, 1)
