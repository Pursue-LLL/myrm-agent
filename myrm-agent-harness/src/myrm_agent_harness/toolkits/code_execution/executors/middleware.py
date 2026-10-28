"""Executor middleware base class (decorator pattern).

Injects policy checks before/after execution (e.g. command blocklist, timeout, path restrictions).
Multiple middlewares can be composed into a policy chain.

[INPUT]
- toolkits.code_execution.executors.base::CodeExecutor (POS: Abstract executor the middleware wraps and delegates to)
- toolkits.code_execution.executors.models::ExecutionContext, ExecutionMetrics, ExecutionResult, MCPCommunicationConfig (POS: Executor value objects)

[OUTPUT]
- CodeExecutorMiddleware: Executor that forwards every operation to an inner executor; subclasses override the operations they police.

[POS]
Decorator layer over CodeExecutor. Every new CodeExecutor operation must be forwarded here, otherwise a wrapped executor silently falls back to the shell-based default.
"""

from collections.abc import AsyncIterator

from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor
from myrm_agent_harness.toolkits.code_execution.executors.models import (
    ExecutionContext,
    ExecutionMetrics,
    ExecutionResult,
    MCPCommunicationConfig,
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

    @metrics.setter
    def metrics(self, value: ExecutionMetrics) -> None:
        self.inner.metrics = value

    @property
    def workspace_path(self) -> str:
        return self.inner.workspace_path

    def bind_workspace(self, workspace_path: str) -> None:
        self.inner.bind_workspace(workspace_path)

    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        return await self.inner.execute(context)

    async def execute_bash(self, context: ExecutionContext) -> ExecutionResult:
        return await self.inner.execute_bash(context)

    async def execute_bash_stream(self, context: ExecutionContext) -> AsyncIterator[str]:
        async for chunk in self.inner.execute_bash_stream(context):
            yield chunk

    async def read_file(self, path: str) -> str:
        return await self.inner.read_file(path)

    async def read_file_bytes(self, path: str) -> bytes:
        return await self.inner.read_file_bytes(path)

    async def write_file(self, path: str, content: str) -> None:
        await self.inner.write_file(path, content)

    async def write_file_bytes(self, path: str, content: bytes) -> None:
        await self.inner.write_file_bytes(path, content)

    async def append_file(self, path: str, content: str) -> None:
        await self.inner.append_file(path, content)

    async def delete_file(self, path: str) -> None:
        await self.inner.delete_file(path)

    async def file_exists(self, path: str) -> bool:
        return await self.inner.file_exists(path)

    async def is_file(self, path: str) -> bool:
        return await self.inner.is_file(path)

    async def is_dir(self, path: str) -> bool:
        return await self.inner.is_dir(path)

    async def file_size(self, path: str) -> int:
        return await self.inner.file_size(path)

    async def mkdir(self, path: str) -> None:
        await self.inner.mkdir(path)

    async def list_files(self, path: str = ".", pattern: str = "*") -> list[str]:
        return await self.inner.list_files(path, pattern)

    async def resolve_path(self, relative_path: str) -> str:
        return await self.inner.resolve_path(relative_path)

    async def is_available(self) -> bool:
        return await self.inner.is_available()

    def get_executor_name(self) -> str:
        return self.inner.get_executor_name()

    def get_mcp_communication_config(self) -> MCPCommunicationConfig | None:
        return self.inner.get_mcp_communication_config()

    async def save_workspace(self, session_id: str, storage_path: str) -> bool:
        return await self.inner.save_workspace(session_id, storage_path)

    async def restore_workspace(self, session_id: str, storage_path: str) -> bool:
        return await self.inner.restore_workspace(session_id, storage_path)

    async def close(self) -> None:
        await self.inner.close()
