"""The YOLO grant the unattended goal trigger gives its headless run stays in that run's params."""

from __future__ import annotations

import copy

import pytest

from .trigger_testkit import trigger_goal_turns, user_configs

_SAVED_YOLO_OFF: dict[str, object] = {"yoloModeEnabled": False, "approvalTimeoutSeconds": 120}
_SAVED_YOLO_ON: dict[str, object] = {"yolo_mode_enabled": True, "yolo_mode_enabled_at": 5.0, "yolo_mode_timeout": 60}


@pytest.mark.asyncio
async def test_the_grant_does_not_leak_into_the_cached_saved_config() -> None:
    """The loader hands every reader the dict it cached for the next 30 s. The grant (YOLO on, no time limit) goes
    into the run's own copy, so that dict, read next by any other chat or channel, stays what the user saved."""
    cached = user_configs(copy.deepcopy(_SAVED_YOLO_OFF))

    await trigger_goal_turns("chat-goal-grant", turns=1, configs=cached)

    assert cached.security_config_dict == _SAVED_YOLO_OFF


@pytest.mark.asyncio
async def test_a_saved_config_without_yolo_is_granted_it_without_a_time_limit() -> None:
    """The headless run has nobody to approve a tool, so it runs with YOLO on and keeps the rest of what the user saved."""
    (params,) = await trigger_goal_turns("chat-goal-grant", turns=1, configs=user_configs(copy.deepcopy(_SAVED_YOLO_OFF)))

    assert params.security_config_raw is not None
    assert params.security_config_raw["yolo_mode_enabled"] is True
    assert params.security_config_raw["yolo_mode_timeout"] is None
    assert params.security_config_raw["approvalTimeoutSeconds"] == 120


@pytest.mark.asyncio
async def test_a_saved_yolo_keeps_its_own_timer_in_the_run() -> None:
    """A YOLO the user switched on is the user's: the trigger does not restart or lift its time limit."""
    (params,) = await trigger_goal_turns("chat-goal-grant", turns=1, configs=user_configs(copy.deepcopy(_SAVED_YOLO_ON)))

    assert params.security_config_raw == _SAVED_YOLO_ON
