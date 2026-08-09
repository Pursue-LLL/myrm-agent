"""Unit tests for the shared eval SSE status stream helper.

Covers the deduplication and close-frame contract of
``stream_status_events``, which is shared by the single-profile eval,
matrix, and memory A/B status streams.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.api.eval.streaming import stream_status_events


async def _collect_frames(
    statuses: list[dict[str, object]], poll_interval: float = 0.01
) -> list[str]:
    it: Iterator[dict[str, object]] = iter(statuses)
    generator = stream_status_events(lambda: next(it), poll_interval=poll_interval)
    return [frame async for frame in generator]


@pytest.mark.asyncio
async def test_stream_status_events_dedups_unchanged_frames() -> None:
    frames = await _collect_frames(
        [
            {"is_running": True, "stage": "download"},
            {"is_running": True, "stage": "download"},
            {"is_running": False},
        ]
    )
    assert frames == [
        'data: {"is_running": true, "stage": "download"}\n\n',
        'data: {"is_running": false}\n\n',
        "event: close\ndata: {}\n\n",
    ]


@pytest.mark.asyncio
async def test_stream_status_events_emits_state_change() -> None:
    frames = await _collect_frames(
        [
            {"is_running": True, "stage": "download"},
            {"is_running": True, "stage": "run", "progress": 50},
            {"is_running": False},
        ]
    )
    assert frames == [
        'data: {"is_running": true, "stage": "download"}\n\n',
        'data: {"is_running": true, "stage": "run", "progress": 50}\n\n',
        'data: {"is_running": false}\n\n',
        "event: close\ndata: {}\n\n",
    ]


@pytest.mark.asyncio
async def test_stream_status_events_closes_immediately_when_not_running() -> None:
    frames = await _collect_frames([{"is_running": False}])
    assert frames == ['data: {"is_running": false}\n\n', "event: close\ndata: {}\n\n"]
