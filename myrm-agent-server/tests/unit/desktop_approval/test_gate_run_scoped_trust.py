"""Unit tests for run-scoped (cron blueprint) desktop trust + unattended fail-fast."""

from __future__ import annotations

import asyncio

from app.ai_agents.desktop_control.gate import DesktopControlGate


def _run(coro):
    return asyncio.run(coro)


def _call(gate: DesktopControlGate, *, app_name: str, app_id: str = ""):
    return _run(
        gate(
            reason="test",
            operation="interact",
            estimated_duration_seconds=1.0,
            timeout_seconds=0.05,
            app_name=app_name,
            app_id=app_id,
        )
    )


def test_run_scoped_key_grants_without_prompt():
    gate = DesktopControlGate(
        workspace_root=None,
        register_live=False,
        preapproved_trust_keys=["sap gui"],
    )
    result = _call(gate, app_name="SAP GUI")
    assert result.granted is True


def test_run_scoped_key_does_not_grant_other_apps():
    gate = DesktopControlGate(
        workspace_root=None,
        register_live=False,
        preapproved_trust_keys=["sap gui"],
        unattended_fail_fast=True,
    )
    result = _call(gate, app_name="Unknown App")
    assert result.granted is False


def test_unattended_fail_fast_denies_without_wait():
    import time

    gate = DesktopControlGate(
        workspace_root=None,
        register_live=False,
        unattended_fail_fast=True,
    )
    started = time.monotonic()
    result = _call(gate, app_name="SAP GUI")
    assert result.granted is False
    assert time.monotonic() - started < 5.0


def test_interactive_default_still_blocks_without_trust():
    # No fail-fast: no progress sink in unit context -> denied via sink-None path.
    gate = DesktopControlGate(workspace_root=None, register_live=False)
    result = _call(gate, app_name="SAP GUI")
    assert result.granted is False
