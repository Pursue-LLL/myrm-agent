"""A TLS toggle made while the server runs reaches the next model request, in either direction.

A model transport client keeps the TLS context it was built with, so the toggle retires the shared clients; without
that, turning the relaxation off would leave relaxed clients in use until a restart.
"""

from __future__ import annotations

import os

import pytest

from app.core.infra import tls_config

_ENV = "MYRM_TLS_STRICT"


@pytest.fixture
def toggled(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """What the toggle did, in order: the policy install, and the value of ``MYRM_TLS_STRICT`` each time the clients were retired."""
    events: list[str | None] = []
    # monkeypatch restores the variable however the code under test changes it.
    monkeypatch.setenv(_ENV, "1")
    monkeypatch.setattr(
        "myrm_agent_harness.infra.tls_compat.apply_global_tls_relaxation", lambda: events.append("installed") or True
    )
    monkeypatch.setattr(tls_config, "retire_clients", lambda: events.append(f"retired:{os.environ.get(_ENV)}"))
    return events


def test_turning_the_relaxation_on_installs_the_policy_then_retires_the_clients(toggled: list[str | None]) -> None:
    tls_config.sync_tls_env_from_config({"enterpriseTlsCompat": True})

    assert os.environ[_ENV] == "0"
    assert toggled == ["installed", "retired:0"]


def test_turning_it_off_restores_strict_verification_and_retires_the_clients_that_were_built_relaxed(
    toggled: list[str | None],
) -> None:
    tls_config.sync_tls_env_from_config({"enterpriseTlsCompat": False})

    assert _ENV not in os.environ
    assert toggled == ["retired:None"]


@pytest.mark.parametrize("settings", [{}, {"enterpriseTlsCompat": "yes"}, {"enterpriseTlsCompat": None}])
def test_anything_but_true_is_off(settings: dict[str, object], toggled: list[str | None]) -> None:
    tls_config.sync_tls_env_from_config(settings)

    assert _ENV not in os.environ
    assert toggled == ["retired:None"]
