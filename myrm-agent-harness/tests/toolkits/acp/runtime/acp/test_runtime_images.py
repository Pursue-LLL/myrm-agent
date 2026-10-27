"""AcpRuntime sends a turn's images as image blocks to an agent that advertises them, and says so when it cannot."""

from __future__ import annotations

import base64
import hashlib
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.acp.types import IMAGES_NOT_SENT_STATUS, RuntimeEvent, RuntimeEventType

from ._fakes import make_png, make_pool, run_turn

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the scripted ACP agent is exercised on POSIX only")


def _digest(body: bytes) -> str:
    """What the mock agent reports for an image block that carries ``body``."""
    data = base64.b64encode(body).decode("ascii")
    return f"image/png:{len(data)}:{hashlib.sha256(data.encode()).hexdigest()[:16]}"


def _not_sent_notices(events: list[RuntimeEvent]) -> list[RuntimeEvent]:
    return [
        event
        for event in events
        if event.type == RuntimeEventType.STATUS_UPDATE and event.data.get("status") == IMAGES_NOT_SENT_STATUS
    ]


class TestImagePrompts:
    @pytest.mark.asyncio
    async def test_an_agent_that_advertises_image_prompts_receives_the_images_in_order(self, tmp_path: Path) -> None:
        first, first_body = make_png(tmp_path, "a.png", 4_000)
        second, second_body = make_png(tmp_path, "b.png", 9_000)
        pool = make_pool(tmp_path, "--images")
        try:
            text, events = await run_turn(pool, [str(first), str(second)])
        finally:
            await pool.close_all()

        assert "[echo] look at this" in text
        assert f"[images] {_digest(first_body)} {_digest(second_body)}" in text
        assert _not_sent_notices(events) == []

    @pytest.mark.asyncio
    async def test_an_image_of_the_largest_size_the_server_stages_arrives_whole(self, tmp_path: Path) -> None:
        image, body = make_png(tmp_path, "big.png", 5 * 1024 * 1024)
        pool = make_pool(tmp_path, "--images")
        try:
            text, events = await run_turn(pool, [str(image)])
        finally:
            await pool.close_all()

        assert f"[images] {_digest(body)}" in text
        assert events[-1].type == RuntimeEventType.DONE

    @pytest.mark.asyncio
    async def test_an_agent_that_does_not_advertise_image_prompts_gets_the_text_and_the_turn_says_so(
        self, tmp_path: Path
    ) -> None:
        first, _ = make_png(tmp_path, "a.png", 4_000)
        second, _ = make_png(tmp_path, "b.png", 5_000)
        pool = make_pool(tmp_path)
        try:
            text, events = await run_turn(pool, [str(first), str(second)])
        finally:
            await pool.close_all()

        assert "[echo] look at this" in text
        assert "[images]" not in text
        assert events[-1].type == RuntimeEventType.DONE
        notices = _not_sent_notices(events)
        assert [notice.data.get("images") for notice in notices] == [2]
        assert events.index(notices[0]) < next(i for i, e in enumerate(events) if e.type == RuntimeEventType.TEXT_DELTA)

    @pytest.mark.asyncio
    async def test_a_turn_without_images_sends_the_text_alone(self, tmp_path: Path) -> None:
        pool = make_pool(tmp_path, "--images")
        try:
            text, events = await run_turn(pool, [])
        finally:
            await pool.close_all()

        assert "[echo] look at this" in text
        assert "[images]" not in text
        assert _not_sent_notices(events) == []
