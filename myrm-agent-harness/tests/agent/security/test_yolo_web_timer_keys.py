"""The YOLO time limit the web UI saves (camelCase keys) is enforced, and a server-side grant outranks it.

The web UI stores ``yoloModeEnabled`` with ``yoloModeTimeout`` and ``yoloModeEnabledAt`` (epoch seconds); a server
grant writes the snake_case counterparts. Both must reach ``SecurityConfig`` so that an expired YOLO is off even when
no browser tab is open to switch it off.
"""

from __future__ import annotations

import time

import pytest

from myrm_agent_harness.agent.middlewares.approval.batch_processor import is_yolo_mode_active
from myrm_agent_harness.agent.security.config import parse_security_config
from myrm_agent_harness.agent.security.types import SecurityConfig


def _parsed(raw: dict[str, object]) -> SecurityConfig:
    config = parse_security_config(raw)
    assert config is not None
    return config


def test_the_web_timer_keys_reach_the_security_config() -> None:
    config = _parsed({"yoloModeEnabled": True, "yoloModeTimeout": 600, "yoloModeEnabledAt": 1_700_000_000})

    assert config.yolo_mode_timeout == 600
    assert config.yolo_mode_enabled_at == pytest.approx(1_700_000_000.0)


def test_a_web_yolo_is_active_within_its_time_limit() -> None:
    config = _parsed({"yoloModeEnabled": True, "yoloModeTimeout": 600, "yoloModeEnabledAt": time.time() - 10})

    assert is_yolo_mode_active(config)


def test_a_web_yolo_is_off_once_its_time_limit_has_run_out() -> None:
    config = _parsed({"yoloModeEnabled": True, "yoloModeTimeout": 600, "yoloModeEnabledAt": time.time() - 700})

    assert not is_yolo_mode_active(config)


def test_a_web_yolo_without_a_time_limit_stays_active() -> None:
    config = _parsed({"yoloModeEnabled": True, "yoloModeEnabledAt": time.time() - 100_000})

    assert config.yolo_mode_timeout is None
    assert is_yolo_mode_active(config)


def test_a_start_time_that_cannot_be_read_counts_as_long_past() -> None:
    config = _parsed({"yoloModeEnabled": True, "yoloModeTimeout": 600, "yoloModeEnabledAt": "2026-01-01T00:00:00Z"})

    assert not is_yolo_mode_active(config)


def test_server_grant_keys_outrank_the_web_timer() -> None:
    now = time.time()
    config = _parsed(
        {
            "yoloModeEnabled": True,
            "yoloModeTimeout": 600,
            "yoloModeEnabledAt": now - 10_000,
            "yolo_mode_enabled": True,
            "yolo_mode_timeout": 30,
            "yolo_mode_enabled_at": now,
        }
    )

    assert config.yolo_mode_timeout == 30
    assert config.yolo_mode_enabled_at == pytest.approx(now, abs=1.0)
    assert is_yolo_mode_active(config)


def test_a_server_grant_without_a_time_limit_does_not_inherit_the_web_timer() -> None:
    config = _parsed(
        {
            "yoloModeEnabled": True,
            "yoloModeTimeout": 600,
            "yoloModeEnabledAt": time.time() - 10_000,
            "yolo_mode_enabled": True,
            "yolo_mode_timeout": None,
            "yolo_mode_enabled_at": time.time(),
        }
    )

    assert config.yolo_mode_timeout is None
    assert is_yolo_mode_active(config)
