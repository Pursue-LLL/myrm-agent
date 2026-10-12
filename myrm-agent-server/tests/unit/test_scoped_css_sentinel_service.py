"""Unit tests for ScopedCssSentinelService."""

from __future__ import annotations

import pytest

from app.schemas.scoped_css_sentinel import (
    CheckConflictRequest,
    ConcurrentStylePatchRequest,
    ScopeCssRequest,
)
from app.services.security.scoped_css_sentinel_service import (
    ScopedCssSentinelService,
)


@pytest.fixture
def service() -> ScopedCssSentinelService:
    """Create a fresh ScopedCssSentinelService instance."""
    return ScopedCssSentinelService()


def test_service_scope_css_valid(service: ScopedCssSentinelService) -> None:
    """Verify service correctly scopes valid CSS rules without global leakage."""
    req = ScopeCssRequest(
        css_content=".btn { color: white; background: blue; } .card { padding: 16px; }",
        scope_id="drawer-dialog",
    )
    res = service.scope_css(req)
    assert res.is_valid is True
    assert res.scope_id == "#drawer-dialog"
    assert res.rules_rewritten == 2
    assert "#drawer-dialog .btn" in res.scoped_css
    assert "#drawer-dialog .card" in res.scoped_css


def test_service_scope_css_global_violation(
    service: ScopedCssSentinelService,
) -> None:
    """Verify service rejects unconfined global root selectors."""
    req = ScopeCssRequest(
        css_content="body { margin: 0; } :root { --bg: #fff; }",
        scope_id=".modal-dialog",
    )
    res = service.scope_css(req)
    assert res.is_valid is False
    assert len(res.violations) == 2
    assert res.scoped_css == ""
    assert any("body" in v.selector for v in res.violations)
    assert any(":root" in v.selector for v in res.violations)


def test_service_check_conflicts_orthogonal(
    service: ScopedCssSentinelService,
) -> None:
    """Verify non-overlapping micro-agent patches merge cleanly."""
    patch_1 = ConcurrentStylePatchRequest(
        agent_id="header_agent",
        component_target_id="app-header",
        css_content=".nav { display: flex; }",
    )
    patch_2 = ConcurrentStylePatchRequest(
        agent_id="sidebar_agent",
        component_target_id="app-sidebar",
        css_content=".menu { list-style: none; }",
    )
    req = CheckConflictRequest(patches=[patch_1, patch_2])
    res = service.check_conflicts(req)
    assert res.has_conflict is False
    assert res.conflicting_agents == []
    assert res.merged_scoped_css is not None
    assert "#app-header .nav" in res.merged_scoped_css
    assert "#app-sidebar .menu" in res.merged_scoped_css


def test_service_check_conflicts_collision(
    service: ScopedCssSentinelService,
) -> None:
    """Verify simultaneous patches targeting the same component trigger collision failure."""
    patch_a = ConcurrentStylePatchRequest(
        agent_id="agent_1",
        component_target_id="hero-banner",
        css_content=".title { font-size: 24px; }",
    )
    patch_b = ConcurrentStylePatchRequest(
        agent_id="agent_2",
        component_target_id="hero-banner",
        css_content=".title { font-size: 32px; }",
    )
    req = CheckConflictRequest(patches=[patch_a, patch_b])
    res = service.check_conflicts(req)
    assert res.has_conflict is True
    assert set(res.conflicting_agents) == {"agent_1", "agent_2"}
    assert "collision detected" in res.reason
    assert res.merged_scoped_css is None
