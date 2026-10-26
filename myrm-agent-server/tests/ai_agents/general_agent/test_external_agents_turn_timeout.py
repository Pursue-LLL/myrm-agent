"""How long one delegated CLI turn may run."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.ai_agents.general_agent.external_agents_runtime_config import (
    _config_fingerprint,
    _register_backends_on_pool,
    _turn_timeout,
)
from app.config.settings import settings

_DEFAULT = 1800


@pytest.mark.parametrize("raw", [None, 0, -1, -300, "", "abc", "0", True, 1.5, [], {}])
def test_a_missing_or_unusable_timeout_means_the_default(raw: object) -> None:
    assert _turn_timeout({"timeout": raw}) == _DEFAULT
    assert _turn_timeout({}) == _DEFAULT


@pytest.mark.parametrize(("raw", "seconds"), [(120, 120), (300, 300), ("900", 900), (" 45 ", 45)])
def test_a_usable_timeout_is_kept(raw: object, seconds: int) -> None:
    assert _turn_timeout({"timeout": raw}) == seconds


def test_a_timeout_longer_than_the_gateway_allows_is_brought_under_its_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.agent, "execution_hard_ceiling", 3600.0)

    assert _turn_timeout({"timeout": 7200}) == 3540
    assert _turn_timeout({"timeout": 3540}) == 3540
    assert _turn_timeout({"timeout": 3000}) == 3000


def test_the_default_also_stays_under_a_lower_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.agent, "execution_hard_ceiling", 600.0)

    assert _turn_timeout({}) == 540


def test_a_ceiling_below_the_margin_still_leaves_a_positive_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.agent, "execution_hard_ceiling", 30.0)

    assert _turn_timeout({}) == 1


def test_the_registered_backend_gets_the_normalized_timeout() -> None:
    pool = MagicMock()

    _register_backends_on_pool(pool, [{"name": "claude", "command": "claude"}])
    _register_backends_on_pool(pool, [{"name": "codex", "command": "codex", "timeout": 120}])
    _register_backends_on_pool(pool, [{"name": "broken", "command": "broken", "timeout": 0}])

    registered = {call.args[0]: call.args[1].timeout_seconds for call in pool.register.call_args_list}
    assert registered == {"claude": _DEFAULT, "codex": 120, "broken": _DEFAULT}


def test_spelling_out_the_default_does_not_change_the_pool_fingerprint() -> None:
    implicit = {"name": "claude", "command": "claude"}
    explicit = {"name": "claude", "command": "claude", "timeout": _DEFAULT}
    invalid = {"name": "claude", "command": "claude", "timeout": 0}

    assert _config_fingerprint([implicit]) == _config_fingerprint([explicit]) == _config_fingerprint([invalid])
