"""A status reaction that keeps failing is reported once per window, not swallowed and not spammed.

The reaction is best-effort, so a failure never reaches the turn. But a bot without the reaction
permission (Slack ``reactions:write``, Feishu reaction scope) failed at debug level on every turn,
which looked like a working bot with no status indicator.
"""

from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.message_effects import MessageEffects
from app.channels.types import ChannelCapabilities

EYES = "\U0001f440"
LOGGER = "app.channels.routing.message_effects"


def _effects(error: Exception | None) -> tuple[MessageEffects, AsyncMock]:
    ch = MagicMock()
    ch.capabilities = ChannelCapabilities(reactions=True)
    ch.react_to_message = AsyncMock(side_effect=error)
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=ch)
    return MessageEffects(bus), ch.react_to_message


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and r.name == LOGGER]


@pytest.mark.asyncio
async def test_a_failure_is_warned_with_the_channel_and_the_reason(caplog: pytest.LogCaptureFixture) -> None:
    fx, _ = _effects(RuntimeError("missing_scope (needs scope reactions:write)"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await fx.set_reaction("slack", "C1", "m1", EYES)

    [warning] = _warnings(caplog)
    assert "slack" in warning
    assert "missing_scope (needs scope reactions:write)" in warning


@pytest.mark.asyncio
async def test_a_failure_never_reaches_the_caller() -> None:
    fx, _ = _effects(RuntimeError("denied"))
    await fx.set_reaction("slack", "C1", "m1", EYES)


@pytest.mark.asyncio
async def test_the_same_failure_is_warned_once_per_window(caplog: pytest.LogCaptureFixture) -> None:
    fx, _ = _effects(RuntimeError("denied"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await fx.set_reaction("slack", "C1", "m1", EYES)
        await fx.set_reaction("slack", "C1", "m2", EYES)
        await fx.set_reaction("slack", "C2", "m3", "")

    assert len(_warnings(caplog)) == 1


@pytest.mark.asyncio
async def test_the_failure_is_warned_again_when_the_window_has_passed(caplog: pytest.LogCaptureFixture) -> None:
    fx, _ = _effects(RuntimeError("denied"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await fx.set_reaction("slack", "C1", "m1", EYES)
        fx._reaction_warned_at[("slack", "RuntimeError")] = time.monotonic() - 3600
        await fx.set_reaction("slack", "C1", "m2", EYES)

    assert len(_warnings(caplog)) == 2


@pytest.mark.asyncio
async def test_another_channel_is_warned_separately(caplog: pytest.LogCaptureFixture) -> None:
    fx, _ = _effects(RuntimeError("denied"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await fx.set_reaction("slack", "C1", "m1", EYES)
        await fx.set_reaction("feishu", "oc1", "m1", EYES)

    assert len(_warnings(caplog)) == 2


@pytest.mark.asyncio
async def test_another_kind_of_failure_on_the_same_channel_is_warned_separately(caplog: pytest.LogCaptureFixture) -> None:
    fx, react = _effects(RuntimeError("denied"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await fx.set_reaction("slack", "C1", "m1", EYES)
        react.side_effect = TimeoutError("slow")
        await fx.set_reaction("slack", "C1", "m2", EYES)

    assert len(_warnings(caplog)) == 2


@pytest.mark.asyncio
async def test_a_working_reaction_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    fx, _ = _effects(None)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await fx.set_reaction("slack", "C1", "m1", EYES)

    assert not _warnings(caplog)
