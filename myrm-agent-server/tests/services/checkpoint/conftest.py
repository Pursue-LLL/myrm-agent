"""Fixtures shared by the SnapshotInterceptor test modules."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.services.checkpoint.snapshot_service import SnapshotInterceptor, _workspace_locks


@pytest.fixture(autouse=True)
def _clear_workspace_locks() -> Iterator[None]:
    """Reset module-level locks between tests."""
    _workspace_locks.clear()
    yield
    _workspace_locks.clear()


@pytest.fixture
def interceptor() -> SnapshotInterceptor:
    return SnapshotInterceptor()
