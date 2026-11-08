"""Shutdown closes the model transport's shared HTTP clients once nothing can still call a model.

Clients left open drop their connections abruptly when the process exits. The order is the point: closing before the
background tasks (skill review, memory extraction) finish would cut the model calls they still make, and a close that
hangs must not hold back the database flush that follows.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import logging
import time

import pytest
from myrm_agent_harness.toolkits.llms import transport

from app.server import shutdown as shutdown_helpers
from app.server.lifespan.shutdown import _shutdown


def _awaited_call_lines() -> dict[str, int]:
    """Every awaited call of ``_shutdown`` (by callee or attribute name) -> the line of its first occurrence."""
    first_line: dict[str, int] = {}
    for node in ast.walk(ast.parse(inspect.getsource(_shutdown))):
        if not isinstance(node, ast.Await) or not isinstance(node.value, ast.Call):
            continue
        callee = node.value.func
        name = callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", "")
        first_line.setdefault(name, node.lineno)
    return first_line


def test_the_clients_close_after_every_component_that_may_call_a_model_and_before_the_database_flush() -> None:
    awaited = _awaited_call_lines()

    assert "safe_close_model_transport" in awaited, "_shutdown must close the model transport's clients"
    assert awaited["gather"] < awaited["safe_close_model_transport"] < awaited["dispose"]


@pytest.mark.asyncio
async def test_it_awaits_the_transports_close(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[bool] = []

    async def close() -> None:
        closed.append(True)

    monkeypatch.setattr(transport, "aclose_clients", close)

    await shutdown_helpers.safe_close_model_transport()

    assert closed == [True]


@pytest.mark.asyncio
async def test_a_failing_close_is_logged_and_does_not_stop_the_shutdown(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def close() -> None:
        raise RuntimeError("socket gone")

    monkeypatch.setattr(transport, "aclose_clients", close)

    with caplog.at_level(logging.WARNING, logger=shutdown_helpers.logger.name):
        await shutdown_helpers.safe_close_model_transport()

    assert "Model transport close failed: socket gone" in caplog.text


@pytest.mark.asyncio
async def test_a_close_that_hangs_is_cut_off_at_the_bound(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def hang() -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(transport, "aclose_clients", hang)
    monkeypatch.setattr(shutdown_helpers, "_MODEL_TRANSPORT_CLOSE_TIMEOUT_SECONDS", 0.05)

    started = time.monotonic()
    with caplog.at_level(logging.WARNING, logger=shutdown_helpers.logger.name):
        await shutdown_helpers.safe_close_model_transport()

    assert time.monotonic() - started < 1.0
    assert "Model transport close failed" in caplog.text
