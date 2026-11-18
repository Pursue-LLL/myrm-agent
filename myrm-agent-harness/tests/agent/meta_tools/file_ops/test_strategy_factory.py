"""Unit tests for FileSystemStrategyFactory."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.executor_storage_adapter import ExecutorStorageAdapter
from myrm_agent_harness.agent.meta_tools.file_ops.strategies.base import FileSystemStrategy
from myrm_agent_harness.agent.meta_tools.file_ops.strategies.mcp_strategy import (
    MCPFileSystemStrategy,
)
from myrm_agent_harness.agent.meta_tools.file_ops.strategies.storage_strategy import (
    StorageBackendStrategy,
)
from myrm_agent_harness.agent.meta_tools.file_ops.strategies.strategy_factory import (
    FileSystemStrategyFactory,
)
from myrm_agent_harness.toolkits.code_execution.executors.base import (
    reset_executor,
    set_executor,
)


def _executor_at(workspace_path: str) -> MagicMock:
    executor = MagicMock()
    executor.workspace_path = workspace_path
    return executor


def _executor_workspace(strategy: FileSystemStrategy) -> str:
    """The workspace of the executor a strategy reaches its files through."""
    assert isinstance(strategy, StorageBackendStrategy)
    assert isinstance(strategy.storage, ExecutorStorageAdapter)
    return strategy.storage.workspace_path


def test_create_strategy_mcp_path() -> None:
    strategy = FileSystemStrategyFactory.create_strategy("/mcp/some_skill/doc.md", [])
    assert isinstance(strategy, MCPFileSystemStrategy)


def test_create_strategy_with_explicit_executor() -> None:
    strategy = FileSystemStrategyFactory.create_strategy("some/file.py", [], executor=_executor_at("/explicit"))
    assert _executor_workspace(strategy) == "/explicit"


def test_create_strategy_with_contextvar_executor() -> None:
    token = set_executor(_executor_at("/bound"))
    try:
        strategy = FileSystemStrategyFactory.create_strategy("some/file.py", [])
    finally:
        reset_executor(token)
    assert _executor_workspace(strategy) == "/bound"


def test_the_explicit_executor_wins_over_the_bound_one() -> None:
    token = set_executor(_executor_at("/bound"))
    try:
        strategy = FileSystemStrategyFactory.create_strategy("some/file.py", [], executor=_executor_at("/explicit"))
    finally:
        reset_executor(token)
    assert _executor_workspace(strategy) == "/explicit"


def test_create_strategy_with_storage_backend() -> None:
    mock_backend = MagicMock()
    strategy = FileSystemStrategyFactory.create_strategy("some/file.py", [], storage_backend=mock_backend)
    assert isinstance(strategy, StorageBackendStrategy)
    assert strategy.storage is mock_backend


def test_an_explicit_storage_backend_wins_over_an_explicit_executor() -> None:
    mock_backend = MagicMock()
    strategy = FileSystemStrategyFactory.create_strategy(
        "some/file.py", [], executor=_executor_at("/explicit"), storage_backend=mock_backend
    )
    assert isinstance(strategy, StorageBackendStrategy)
    assert strategy.storage is mock_backend


def test_an_explicit_storage_backend_wins_over_the_bound_executor() -> None:
    mock_backend = MagicMock()
    token = set_executor(_executor_at("/bound"))
    try:
        strategy = FileSystemStrategyFactory.create_strategy("some/file.py", [], storage_backend=mock_backend)
    finally:
        reset_executor(token)
    assert isinstance(strategy, StorageBackendStrategy)
    assert strategy.storage is mock_backend


def test_create_strategy_no_executor_raises() -> None:
    token = set_executor(None)
    try:
        with pytest.raises(ValueError, match="executor or storage_backend is required"):
            FileSystemStrategyFactory.create_strategy("some/file.py", [])
    finally:
        reset_executor(token)
