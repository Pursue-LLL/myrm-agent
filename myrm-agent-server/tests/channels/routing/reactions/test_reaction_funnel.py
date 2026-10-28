"""The reaction funnel: a reaction is best-effort, a failure that keeps happening is reported once per window.

A failure never reaches the turn. But a bot without the reaction permission (Slack ``reactions:write``, Feishu
reaction scope) failing at debug level on every turn looked like a working bot with no status indicator, so it is
warned about once per window per channel and error type, not swallowed and not spammed.
"""

from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.reactions import ReactionFunnel
from app.channels.types import ChannelCapabilities

EYES = "\U0001f440"
LOGGER = "app.channels.routing.reactions.funnel"


def _funnel(error: Exception | None = None, *, channel: MagicMock | None = None) -> tuple[ReactionFunnel, AsyncMock]:
    ch = MagicMock() if channel is None else channel
    ch.capabilities = ChannelCapabilities(reactions=True)
    ch.react_to_message = AsyncMock(side_effect=error)
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=ch)
    return ReactionFunnel(bus), ch.react_to_message


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and r.name == LOGGER]


@pytest.mark.asyncio
async def test_a_failure_is_warned_with_the_channel_and_the_reason(caplog: pytest.LogCaptureFixture) -> None:
    funnel, _ = _funnel(RuntimeError("missing_scope (needs scope reactions:write)"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await funnel.react("slack", "C1", "m1", EYES)

    [warning] = _warnings(caplog)
    assert "slack" in warning
    assert "missing_scope (needs scope reactions:write)" in warning


@pytest.mark.asyncio
async def test_a_failure_never_reaches_the_caller() -> None:
    funnel, _ = _funnel(RuntimeError("denied"))
    await funnel.react("slack", "C1", "m1", EYES)


@pytest.mark.asyncio
async def test_the_same_failure_is_warned_once_per_window(caplog: pytest.LogCaptureFixture) -> None:
    funnel, _ = _funnel(RuntimeError("denied"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await funnel.react("slack", "C1", "m1", EYES)
        await funnel.react("slack", "C1", "m2", EYES)
        await funnel.react("slack", "C2", "m3", "")

    assert len(_warnings(caplog)) == 1


@pytest.mark.asyncio
async def test_the_failure_is_warned_again_when_the_window_has_passed(caplog: pytest.LogCaptureFixture) -> None:
    funnel, _ = _funnel(RuntimeError("denied"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await funnel.react("slack", "C1", "m1", EYES)
        funnel._warned_at[("slack", "RuntimeError")] = time.monotonic() - 3600
        await funnel.react("slack", "C1", "m2", EYES)

    assert len(_warnings(caplog)) == 2


@pytest.mark.asyncio
async def test_another_channel_is_warned_separately(caplog: pytest.LogCaptureFixture) -> None:
    funnel, _ = _funnel(RuntimeError("denied"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await funnel.react("slack", "C1", "m1", EYES)
        await funnel.react("feishu", "oc1", "m1", EYES)

    assert len(_warnings(caplog)) == 2


@pytest.mark.asyncio
async def test_another_kind_of_failure_on_the_same_channel_is_warned_separately(caplog: pytest.LogCaptureFixture) -> None:
    funnel, react = _funnel(RuntimeError("denied"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await funnel.react("slack", "C1", "m1", EYES)
        react.side_effect = TimeoutError("slow")
        await funnel.react("slack", "C1", "m2", EYES)

    assert len(_warnings(caplog)) == 2


@pytest.mark.asyncio
async def test_a_working_reaction_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    funnel, _ = _funnel(None)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await funnel.react("slack", "C1", "m1", EYES)

    assert not _warnings(caplog)


class TestReact:
    @pytest.mark.asyncio
    async def test_the_reaction_reaches_the_channel(self) -> None:
        funnel, react = _funnel()
        await funnel.react("slack", "C1", "m1", EYES)
        react.assert_awaited_once_with("C1", "m1", EYES)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("message_id", [12345, "", None])
    async def test_a_message_without_a_platform_id_is_not_reacted_to(self, message_id: object) -> None:
        funnel, react = _funnel()
        await funnel.react("slack", "C1", message_id, EYES)
        react.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_channel_that_does_not_support_reactions_is_not_asked(self) -> None:
        funnel, react = _funnel()
        funnel._bus.get_channel.return_value.capabilities = ChannelCapabilities(reactions=False)
        await funnel.react("slack", "C1", "m1", EYES)
        react.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_unknown_channel_is_skipped(self) -> None:
        bus = MagicMock()
        bus.get_channel = MagicMock(return_value=None)
        await ReactionFunnel(bus).react("nowhere", "C1", "m1", EYES)


class TestAccepted:
    @staticmethod
    def _funnel(glyphs: frozenset[str] | None, *, known: bool = True) -> ReactionFunnel:
        ch = MagicMock()
        ch.capabilities = ChannelCapabilities(reactions=True, reaction_glyphs=glyphs)
        bus = MagicMock()
        bus.get_channel = MagicMock(return_value=ch if known else None)
        return ReactionFunnel(bus)

    def test_the_preferred_glyph_wins_when_the_platform_takes_it(self) -> None:
        assert self._funnel(None).accepted("c", EYES, ("a", "b")) == EYES

    def test_the_first_fallback_the_platform_takes_is_used(self) -> None:
        assert self._funnel(frozenset({"b"})).accepted("c", EYES, ("a", "b")) == "b"

    def test_nothing_is_chosen_when_the_platform_takes_none(self) -> None:
        assert self._funnel(frozenset({"z"})).accepted("c", EYES, ("a", "b")) == ""

    def test_an_empty_preferred_glyph_switches_the_reaction_off_without_a_fallback(self) -> None:
        assert self._funnel(None).accepted("c", "", ("a", "b")) == ""

    def test_an_unknown_channel_accepts_nothing(self) -> None:
        assert self._funnel(None, known=False).accepted("c", EYES, ("a",)) == ""
