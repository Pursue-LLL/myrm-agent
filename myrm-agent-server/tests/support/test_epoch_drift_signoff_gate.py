"""R278: signoff must not pytest.skip on epoch drift entry gate."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[1]
_DEV_LIB = _SERVER_ROOT.parents[1] / "scripts" / "dev" / "lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))


def test_epoch_drift_entry_skip_bypassed_when_e2e_signoff() -> None:
    from tests.conftest import _epoch_drift_entry_skip_if_shared

    request = MagicMock()
    with patch.dict(os.environ, {"E2E_SIGNOFF": "1"}, clear=False):
        _epoch_drift_entry_skip_if_shared(request)


def test_epoch_drift_entry_skip_bypassed_when_desktop_soak() -> None:
    from tests.conftest import _epoch_drift_entry_skip_if_shared

    request = MagicMock()
    with patch.dict(os.environ, {"MYRM_E2E_DESKTOP_SOAK": "1"}, clear=False):
        _epoch_drift_entry_skip_if_shared(request)


def test_epoch_drift_entry_skip_bypassed_when_launch_force_attach() -> None:
    from tests.conftest import _epoch_drift_entry_skip_if_shared

    request = MagicMock()
    blocked_ctx = MagicMock(
        epoch_match=False,
        blocked=True,
        blocked_reason="no backend at workspace epoch (4 active leases)",
        candidates=(),
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"E2E_SIGNOFF", "MYRM_E2E_EPOCH_DRIFT_GUARD_DISABLE"}
    }
    env["MYRM_E2E_LAUNCH_FORCE"] = "1"
    env["MYRM_CHROME_E2E_ATTACH"] = "1"
    with patch.dict(os.environ, env, clear=True):
        with patch(
            "tests.conftest._chrome_e2e_profile",
            return_value=("SHARED", "NAMESPACE_WRITE", "STANDARD"),
        ):
            with patch(
                "e2e_core.api_verify.resolve_e2e_api_context",
                return_value=blocked_ctx,
            ):
                _epoch_drift_entry_skip_if_shared(request)


def test_epoch_drift_entry_skip_raises_when_not_signoff() -> None:
    from tests.conftest import _epoch_drift_entry_skip_if_shared

    request = MagicMock()
    blocked_ctx = MagicMock(
        epoch_match=False,
        blocked=True,
        blocked_reason="no backend at workspace epoch (1 active leases)",
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"E2E_SIGNOFF", "MYRM_E2E_EPOCH_DRIFT_GUARD_DISABLE"}
    }
    with patch.dict(os.environ, env, clear=True):
        with patch(
            "tests.conftest._chrome_e2e_profile",
            return_value=("SHARED", "NAMESPACE_WRITE", "DESKTOP"),
        ):
            with patch(
                "e2e_core.api_verify.resolve_e2e_api_context",
                return_value=blocked_ctx,
            ):
                with pytest.raises(pytest.skip.Exception) as exc_info:
                    _epoch_drift_entry_skip_if_shared(request)
    assert "epoch drift entry gate" in str(exc_info.value)
