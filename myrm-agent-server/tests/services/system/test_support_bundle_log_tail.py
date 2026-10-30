"""The support bundle reads only the end of a long event log, from the first whole line inside the window."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.system.support_bundle_service import _read_log_tail
from tests.support.event_log_lines import event_line, jsonl_pad


@pytest.mark.parametrize("window", [600, 601, 10_000])
def test_a_log_no_longer_than_the_window_is_read_whole(tmp_path: Path, window: int) -> None:
    log = tmp_path / "session.jsonl"
    log.write_text(jsonl_pad(200) * 3, encoding="utf-8")

    assert _read_log_tail(log, window) == jsonl_pad(200) * 3


def test_a_longer_log_is_read_from_the_first_whole_line_inside_the_window(tmp_path: Path) -> None:
    lines = [event_line(seq, "tool_end", payload_size=50) for seq in range(1, 41)]
    log = tmp_path / "session.jsonl"
    log.write_text("".join(lines), encoding="utf-8")
    window = len(lines[0].encode("utf-8")) * 5 + 17  # starts inside the sixth line from the end

    tail = _read_log_tail(log, window)

    assert tail == "".join(lines[-5:])


def test_a_window_that_starts_on_a_line_boundary_keeps_that_line(tmp_path: Path) -> None:
    lines = [jsonl_pad(100) for _ in range(10)]
    log = tmp_path / "session.jsonl"
    log.write_text("".join(lines), encoding="utf-8")

    assert _read_log_tail(log, 300) == "".join(lines[-3:])


@pytest.mark.parametrize("offset_into_character", [0, 1, 2])
def test_a_window_that_starts_inside_a_multibyte_character_does_not_leave_damage(
    tmp_path: Path, offset_into_character: int
) -> None:
    line = json.dumps({"seq": 1, "data": "中" * 50}, ensure_ascii=False) + "\n"
    log = tmp_path / "session.jsonl"
    log.write_text(line * 20, encoding="utf-8")
    window = len(line.encode("utf-8")) * 3 + line.encode("utf-8").index("中".encode("utf-8")) + offset_into_character

    tail = _read_log_tail(log, window)

    assert tail == line * 3


@pytest.mark.parametrize("ending", ["\n", ""])
def test_a_window_inside_one_very_long_line_yields_nothing(tmp_path: Path, ending: str) -> None:
    log = tmp_path / "session.jsonl"
    log.write_text("z" * 5_000 + ending, encoding="utf-8")

    assert _read_log_tail(log, 1_000) == ""
