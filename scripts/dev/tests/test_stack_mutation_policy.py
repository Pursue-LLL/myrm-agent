"""Unit tests for stack_mutation_policy.should_defer_supervisor_backend_heal.

Covers the R143 guard semantics and the backend-down deadlock fix
(api_http_ok=False must never defer backend recovery, otherwise a dead
backend stalls every lease holder and the supervisor refuses to heal).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from stack_mutation_policy import should_defer_supervisor_backend_heal  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_body_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend there are no live E2E sessions in BODY phase."""

    def _fake_list_live_e2e_sessions() -> list[object]:
        return []

    def _fake_body_active_count(_sessions: list[object]) -> int:
        return 0

    monkeypatch.setitem(
        sys.modules,
        "e2e_session_registry",
        type(
            "_FakeRegistry",
            (),
            {
                "list_live_e2e_sessions": staticmethod(_fake_list_live_e2e_sessions),
                "body_active_count": staticmethod(_fake_body_active_count),
            },
        ),
    )


class TestShouldDeferSupervisorBackendHeal:
    def test_backend_down_with_active_leases_never_defers(self) -> None:
        """R143 deadlock fix: a down API must be recovered immediately."""
        assert (
            should_defer_supervisor_backend_heal(
                active_leases=3,
                pending_drift=True,
                api_http_ok=False,
            )
            is False
        )

    def test_backend_down_without_leases_never_defers(self) -> None:
        assert (
            should_defer_supervisor_backend_heal(
                active_leases=0,
                pending_drift=False,
                api_http_ok=False,
            )
            is False
        )

    def test_healthy_backend_with_leases_defers(self) -> None:
        """R143 guard preserved: never restart a healthy backend mid-parallel."""
        assert (
            should_defer_supervisor_backend_heal(
                active_leases=1,
                pending_drift=True,
                api_http_ok=True,
            )
            is True
        )

    def test_healthy_backend_idle_does_not_defer(self) -> None:
        assert (
            should_defer_supervisor_backend_heal(
                active_leases=0,
                pending_drift=True,
                api_http_ok=True,
            )
            is False
        )

    def test_backend_down_defers_despite_body_sessions(self) -> None:
        """Even with E2E sessions in BODY, a down API still recovers."""

        def _fake_body_active_count(_sessions: list[object]) -> int:
            return 2

        sys.modules["e2e_session_registry"].body_active_count = (  # type: ignore[union-attr]
            staticmethod(_fake_body_active_count)
        )
        assert (
            should_defer_supervisor_backend_heal(
                active_leases=0,
                pending_drift=True,
                api_http_ok=False,
            )
            is False
        )
