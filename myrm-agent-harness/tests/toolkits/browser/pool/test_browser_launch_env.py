"""Environment of launched browser processes: secrets filtered, Chromium stamped with its owner and its driver."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.browser.pool.browser_launch_env import camoufox_launch_env, chromium_launch_env
from myrm_agent_harness.toolkits.browser.pool.driver_leftovers import DRIVER_ENV_VAR
from myrm_agent_harness.toolkits.browser.process_owner import OWNER_ENV_VAR, owner_stamp_env

_SANITIZE_ENV = "myrm_agent_harness.core.security.process_env.sanitize_env"
_TOKEN = "driver-token"


def test_camoufox_launch_env_sanitizes_host_and_preserves_fingerprint_keys() -> None:
    fingerprint_env = {"MOZ_HEADLESS": "1", "CAMOUFOX_FINGERPRINT": "abc"}

    with patch(_SANITIZE_ENV, return_value={"PATH": "/usr/bin"}):
        merged = camoufox_launch_env(fingerprint_env)

    assert merged["MOZ_HEADLESS"] == "1"
    assert merged["CAMOUFOX_FINGERPRINT"] == "abc"
    assert merged["PATH"] == "/usr/bin"
    assert "AWS_SECRET_ACCESS_KEY" not in merged


def test_camoufox_launch_env_without_fingerprint_uses_sanitize_only() -> None:
    with patch(_SANITIZE_ENV, return_value={"PATH": "/bin"}) as mock_sanitize:
        merged = camoufox_launch_env(None)

    mock_sanitize.assert_called_once()
    assert merged == {"PATH": "/bin"}


def test_chromium_launch_env_is_sanitized_host_env_plus_owner_stamp_and_driver_token() -> None:
    with patch(_SANITIZE_ENV, return_value={"PATH": "/usr/bin"}):
        env = chromium_launch_env(_TOKEN)

    assert env == {"PATH": "/usr/bin", **owner_stamp_env(), DRIVER_ENV_VAR: _TOKEN}


def test_chromium_launch_env_keeps_secrets_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "do-not-leak")

    env = chromium_launch_env(_TOKEN)

    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert OWNER_ENV_VAR in env


def test_chromium_launch_env_names_this_process_even_when_the_host_carries_another_stamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stamp inherited from an outer process must never be passed on as the owner of this browser."""
    monkeypatch.setenv(OWNER_ENV_VAR, "1:1")

    stamp = chromium_launch_env(_TOKEN)[OWNER_ENV_VAR]

    assert stamp.split(":")[0] == str(os.getpid())


def test_chromium_launch_env_names_the_starting_driver_even_when_the_host_carries_another_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token inherited from an outer process must never be passed on as the driver of this browser."""
    monkeypatch.setenv(DRIVER_ENV_VAR, "inherited-token")

    assert chromium_launch_env(_TOKEN)[DRIVER_ENV_VAR] == _TOKEN
