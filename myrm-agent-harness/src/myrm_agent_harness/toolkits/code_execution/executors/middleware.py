"""Executor middleware base class (decorator pattern).

Injects policy checks before/after execution (e.g. command blocklist, timeout, path restrictions).
Multiple middlewares can be composed into a policy chain.

[INPUT]
- toolkits.code_execution.executors.base::CodeExecutor (POS: Abstract executor the middleware wraps and delegates to)
- toolkits.code_execution.executors.models::AsyncProcessProtocol, ExecutionContext, ExecutionMetrics, ExecutionResult (POS: Executor value objects)

[OUTPUT]
- CodeExecutorMiddleware: Executor that forwards every operation to an inner executor; subclasses override the operations they police.

[POS]
Decorator layer over CodeExecutor. Every CodeExecutor operation is forwarded here, otherwise a wrapped executor silently falls back to the base-class default: shell commands for file operations, no background processes. Its state is the wrapped executor's own: the metrics are the same object, so wrapping an executor that has run commands keeps its counters.
"""

from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import (
    AsyncProcessProtocol,
    ExecutionContext,
    ExecutionMetrics,
    ExecutionResult,
)

__all__ = ["CodeExecutorMiddleware"]


class CodeExecutorMiddleware(CodeExecutor):
    """Executor middleware base class (decorator pattern).

    Injects policy checks before/after execution (e.g. command blocklist, timeout, path restrictions).
    Multiple middlewares can be composed into a policy chain.
    """

    def __init__(self, inner: CodeExecutor):
        self.inner = inner
        super().__init__(config=inner.config)

    @property
    def metrics(self) -> ExecutionMetrics:
        return self.inner.metrics

    @property
    def workspace_path(self) -> str:
        return self.inner.workspace_path

    def bind_workspace(self, workspace_path: str) -> None:
        self.inner.bind_workspace(workspace_path)

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        return await self.inner.execute(context)

    async def execute_bash(self, context: ExecutionContext) -> ExecutionResult:
        return await self.inner.execute_bash(context)

    async def spawn_background_process(self, context: ExecutionContext) -> AsyncProcessProtocol:
        return await self.inner.spawn_background_process(context)

    async def read_file(self, path: str) -> str:
        return await self.inner.read_file(path)

    async def read_file_bytes(self, path: str) -> bytes:
        return await self.inner.read_file_bytes(path)

    async def write_file(self, path: str, content: str) -> None:
        await self.inner.write_file(path, content)

    async def write_file_bytes(self, path: str, content: bytes) -> None:
        await self.inner.write_file_bytes(path, content)

    async def write_file_atomic(self, path: str, content: str) -> None:
        await self.inner.write_file_atomic(path, content)

    async def write_file_bytes_atomic(self, path: str, content: bytes) -> None:
        await self.inner.write_file_bytes_atomic(path, content)

    async def delete_file(self, path: str) -> None:
        await self.inner.delete_file(path)

    async def file_exists(self, path: str) -> bool:
        return await self.inner.file_exists(path)

    async def is_dir(self, path: str) -> bool:
        return await self.inner.is_dir(path)

    async def file_size(self, path: str) -> int:
        return await self.inner.file_size(path)

    async def list_files(self, path: str = ".", pattern: str = "*") -> list[str]:
        return await self.inner.list_files(path, pattern)

    async def resolve_path(self, relative_path: str) -> str:
        return await self.inner.resolve_path(relative_path)

    def get_executor_name(self) -> str:
        return self.inner.get_executor_name()

    def warm_up(self) -> None:
        self.inner.warm_up()

    async def close(self) -> None:
        await self.inner.close()
