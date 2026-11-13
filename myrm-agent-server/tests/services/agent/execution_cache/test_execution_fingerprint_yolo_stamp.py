"""The YOLO enable-time stamp never enters the execution fingerprint; every other security setting still does."""

from __future__ import annotations

import pytest

from app.ai_agents.general_agent.agent import GeneralAgent
from app.core.types import ModelConfig
from app.services.agent.execution_cache.fingerprint import compute_execution_fingerprint

_EARLIER = 1_700_000_000.0
_LATER = 1_700_000_030.0


def _fingerprint(user: dict[str, object] | None = None, agent: dict[str, object] | None = None) -> str:
    return compute_execution_fingerprint(
        GeneralAgent(
            model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
            mcp_config=None,
            security_config_raw=user,
            agent_security_raw=agent,
        )
    )


def _yolo(stamp: float, *, timeout: int | None = None) -> dict[str, object]:
    return {"yolo_mode_enabled": True, "yolo_mode_enabled_at": stamp, "yolo_mode_timeout": timeout}


@pytest.mark.parametrize(
    ("user_timeout", "agent"),
    [
        (None, None),
        (300, None),
        (None, {"yolo_mode_enabled": True, "yolo_mode_timeout": 300}),
    ],
    ids=["no-timeout", "user-timeout", "agent-timeout"],
)
def test_a_user_stamp_does_not_change_the_fingerprint(user_timeout: int | None, agent: dict[str, object] | None) -> None:
    """The goal trigger restamps the user's YOLO state on every run. Whichever side holds a timeout, including an
    agent timeout that counts from this stamp, the stamp is read at run time from the config re-applied each turn."""
    assert _fingerprint(_yolo(_EARLIER, timeout=user_timeout), agent) == _fingerprint(_yolo(_LATER, timeout=user_timeout), agent)


def test_an_agent_stamp_does_not_change_the_fingerprint() -> None:
    assert _fingerprint(agent=_yolo(_EARLIER, timeout=300)) == _fingerprint(agent=_yolo(_LATER, timeout=300))


def test_every_other_security_setting_still_changes_the_fingerprint() -> None:
    baseline = _fingerprint(_yolo(_EARLIER))
    assert _fingerprint({**_yolo(_EARLIER), "yolo_mode_enabled": False}) != baseline
    assert _fingerprint({**_yolo(_EARLIER), "permissions": {"code_interpreter": "ask"}}) != baseline
    assert _fingerprint(_yolo(_EARLIER), {"yolo_mode_enabled": True}) != baseline
    # The timeout is a setting; only the stamp that times it is run-time state.
    assert _fingerprint(_yolo(_EARLIER, timeout=300)) != baseline
    assert _fingerprint(_yolo(_EARLIER, timeout=300)) != _fingerprint(_yolo(_EARLIER, timeout=600))
