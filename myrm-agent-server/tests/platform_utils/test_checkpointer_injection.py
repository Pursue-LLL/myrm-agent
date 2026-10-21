"""Tests for platform_utils checkpointer injection contract."""

import pytest

from app.platform_utils import _reset_checkpointer_for_testing, get_checkpointer, set_checkpointer


def test_get_checkpointer_raises_when_not_initialized() -> None:
    _reset_checkpointer_for_testing()
    with pytest.raises(RuntimeError, match="Checkpointer not initialized"):
        get_checkpointer()


def test_get_checkpointer_returns_injected_instance() -> None:
    from langgraph.checkpoint.memory import MemorySaver

    _reset_checkpointer_for_testing()
    saver = MemorySaver()
    set_checkpointer(saver)
    try:
        assert get_checkpointer() is saver
    finally:
        _reset_checkpointer_for_testing()
