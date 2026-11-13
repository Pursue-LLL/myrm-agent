"""A channel turn's own security values outlast the per-turn reload of the saved securityConfig.

The saved config is reloaded before every stream turn, so a value written into the config dict itself is wiped for every
user who ever saved a security setting (the hosted onboarding saves one for everybody who finishes it). The turn builds an
overlay once and the reload layers it back. These tests run the whole chain a Telegram turn takes: the message, the
preamble, the real reload against a saved config, and the policy the harness ends up enforcing.
"""

from __future__ import annotations

import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.batch_processor.core import is_yolo_mode_active
from myrm_agent_harness.agent.security.engine import evaluate_tool_call
from myrm_agent_harness.agent.security.types import PermissionAction, SecurityConfig

from app.ai_agents.extensions.security_policy_extension import SecurityPolicyExtension, sync_wrapper_security_from_store
from app.channels.types import METADATA_APPROVAL_WINDOW_SECONDS_KEY, InboundMessage
from app.core.channel_bridge.config_loader import UserConfigs

from .preamble_testkit import build_live_turn, inbound_message, minimal_user_configs

_LEARN_QUERY = '[/learn] The user wants you to learn a reusable skill\n2. Save it with the `skill_manage_tool` (action="save").'

# What a user who saved a security setting has stored: any one key makes the whole config a stored one.
_SAVED_CONFIGS = {
    "only_an_approval_window": {"approvalTimeoutSeconds": 120},
    "hosted_onboarding": {"autoReviewEnabled": True, "autoReviewModel": "cheap-model"},
    "yolo_flag_off": {"yoloModeEnabled": False, "permissions": {"*": "ask"}},
}


def _message(**metadata: object) -> InboundMessage:
    msg = inbound_message()
    msg.metadata.update(metadata)
    return msg


def _configs(saved: dict[str, object] | None) -> UserConfigs:
    return replace(minimal_user_configs(), security_config_dict=saved)


async def _reloaded_wrapper(
    msg: InboundMessage,
    saved: dict[str, object] | None,
    *,
    query: str = "test query",
) -> SimpleNamespace:
    """The agent wrapper of ``msg``'s turn after the per-turn reload of ``saved``, as the stream pipeline does it."""
    _result, params = await build_live_turn(msg, configs=_configs(saved), query=query)
    wrapper = SimpleNamespace(security_config_raw=params.security_config_raw, security_overlay=params.security_overlay)
    loaded = SimpleNamespace(security_config_dict=saved)
    with patch("app.core.channel_bridge.config_loader.load_user_configs", new=AsyncMock(return_value=loaded)):
        await sync_wrapper_security_from_store(wrapper)  # type: ignore[arg-type]
    return wrapper


def _enforced(wrapper: SimpleNamespace) -> SecurityConfig:
    """The harness policy of a Telegram turn for the wrapper's config, built the way the stream pipeline builds it."""
    return SecurityPolicyExtension(
        privacy_enabled=False,
        privacy_s2_action="warn",
        privacy_s3_action="redact",
        channel_name="telegram",
        security_config_raw=wrapper.security_config_raw or {},
        agent_security_raw={},
        declared_capabilities=[],
        declared_allowed_roots=[],
    )._build_security_config()


@pytest.mark.parametrize("saved", _SAVED_CONFIGS.values(), ids=_SAVED_CONFIGS.keys())
async def test_a_session_yolo_outlasts_the_reload_of_a_saved_config(saved: dict[str, object]) -> None:
    wrapper = await _reloaded_wrapper(_message(yolo_state=(time.time(), 600)), saved)

    assert is_yolo_mode_active(_enforced(wrapper))


async def test_a_session_yolo_without_a_time_limit_outlasts_the_reload() -> None:
    wrapper = await _reloaded_wrapper(_message(yolo_state=(time.time() - 86_400, None)), _SAVED_CONFIGS["hosted_onboarding"])

    assert is_yolo_mode_active(_enforced(wrapper))


async def test_a_session_yolo_still_expires_after_its_time_limit() -> None:
    wrapper = await _reloaded_wrapper(_message(yolo_state=(time.time() - 700, 600)), _SAVED_CONFIGS["hosted_onboarding"])

    assert not is_yolo_mode_active(_enforced(wrapper))


async def test_a_session_yolo_replaces_a_stored_timer_that_has_run_out() -> None:
    expired = {"yolo_mode_enabled": True, "yolo_mode_enabled_at": time.time() - 7200, "yolo_mode_timeout": 60}

    wrapper = await _reloaded_wrapper(_message(yolo_state=(time.time(), 600)), expired)

    assert is_yolo_mode_active(_enforced(wrapper))


@pytest.mark.parametrize("saved", _SAVED_CONFIGS.values(), ids=_SAVED_CONFIGS.keys())
async def test_a_delegated_approval_window_outlasts_the_reload_of_a_saved_config(saved: dict[str, object]) -> None:
    wrapper = await _reloaded_wrapper(_message(**{METADATA_APPROVAL_WINDOW_SECONDS_KEY: 3600.0}), saved)

    assert _enforced(wrapper).approval_timeout_seconds == 3600


async def test_a_learn_turn_keeps_skill_manage_askable_over_a_saved_deny() -> None:
    saved: dict[str, object] = {"permissions": {"skill_manage": "deny"}}

    wrapper = await _reloaded_wrapper(_message(), saved, query=_LEARN_QUERY)

    action, _reason = evaluate_tool_call("skill_manage", {"action": "save", "name": "demo"}, _enforced(wrapper))
    assert action is PermissionAction.ASK


async def test_an_ordinary_turn_enforces_the_saved_config_as_it_is() -> None:
    saved: dict[str, object] = {"approvalTimeoutSeconds": 120, "permissions": {"skill_manage": "deny"}}

    wrapper = await _reloaded_wrapper(_message(), saved)

    assert wrapper.security_config_raw == saved
    assert not is_yolo_mode_active(_enforced(wrapper))
    action, _reason = evaluate_tool_call("skill_manage", {"action": "save", "name": "demo"}, _enforced(wrapper))
    assert action is PermissionAction.DENY


async def test_a_user_who_saved_nothing_gets_the_turn_values_from_the_build() -> None:
    wrapper = await _reloaded_wrapper(
        _message(yolo_state=(time.time(), 600), **{METADATA_APPROVAL_WINDOW_SECONDS_KEY: 900}),
        None,
    )

    enforced = _enforced(wrapper)
    assert is_yolo_mode_active(enforced)
    assert enforced.approval_timeout_seconds == 900
