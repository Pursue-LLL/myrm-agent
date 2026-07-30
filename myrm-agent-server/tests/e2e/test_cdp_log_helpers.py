"""Unit tests for Chrome E2E backend log helpers."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    count_execution_cache_in_log,
    count_turn_prewarm_in_log,
)


def test_count_turn_prewarm_in_log(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "backend.log"
    log_path.write_text(
        "noise\nTurn prewarm requested: chat_id=c1 agent_id=default\n"
        "Turn prewarm requested: chat_id=c2 agent_id=default\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MYRM_BACKEND_LOG", str(log_path))
    assert count_turn_prewarm_in_log(since_offset=0) == 2
    assert count_turn_prewarm_in_log(since_offset=log_path.stat().st_size) == 0


def test_count_execution_cache_in_log(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "backend.log"
    log_path.write_text(
        "execution_cache_created scope=x\nexecution_cache_reuse scope=x\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MYRM_BACKEND_LOG", str(log_path))
    created, reused = count_execution_cache_in_log(since_offset=0)
    assert created == 1
    assert reused == 1
