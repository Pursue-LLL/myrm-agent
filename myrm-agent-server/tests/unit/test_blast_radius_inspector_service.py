"""Unit tests for BlastRadiusInspectorService."""

from __future__ import annotations

import pytest

from app.schemas.blast_radius_inspector import (
    ActionSurfaceInspectRequest,
    AutoRepairPatchRequest,
    GuardAttributionRequest,
    SinkVulnerabilityDTO,
    ToggleKillSwitchRequest,
)
from app.services.security.blast_radius_inspector_service import (
    BlastRadiusInspectorService,
    get_blast_radius_service,
)


@pytest.fixture
def service() -> BlastRadiusInspectorService:
    return BlastRadiusInspectorService()


def test_singleton_getter() -> None:
    svc1 = get_blast_radius_service()
    svc2 = get_blast_radius_service()
    assert svc1 is svc2


def test_inspect_action_surface(service: BlastRadiusInspectorService) -> None:
    # 1. Normal configuration
    req_normal = ActionSurfaceInspectRequest(
        profile_id="agent_coder",
        tools=["bash", "write_file"],
        declared_file_scopes=["/workspace"],
        declared_api_endpoints=["https://api.github.com"],
        declared_send_channels=["slack_notify"],
        installed_plugins=["myrm_git"],
    )
    res_normal = service.inspect_action_surface(req_normal)
    assert res_normal.profile_id == "agent_coder"
    assert res_normal.pre_admission_allowed is True
    assert res_normal.total_tools_count >= 2
    assert len(res_normal.sinks) > 0

    # 2. Excessive configuration exceeding threshold
    req_excessive = ActionSurfaceInspectRequest(
        profile_id="agent_wildfire",
        tools=["bash", "run_command", "shell_exec", "write_file", "edit_file"],
        declared_file_scopes=["/root", "/etc", "/var"],
        declared_api_endpoints=[f"https://api{i}.domain.com" for i in range(12)],
        declared_send_channels=["email_all", "post_twitter"],
        installed_plugins=["plugin_a", "plugin_b"],
    )
    res_excessive = service.inspect_action_surface(req_excessive)
    assert res_excessive.pre_admission_allowed is False
    assert "Pre-admission rejected" in (res_excessive.admission_rejection_reason or "")


def test_guard_attribution_and_repairs(service: BlastRadiusInspectorService) -> None:
    sample_sink = SinkVulnerabilityDTO(
        action_category="EMAIL",
        dimension="SENDS",
        sink_identifier="email_sender",
        danger_tier="REACHABLE_VERIFIED",
        description="Outbound email communication",
    )

    # Test attribution with active guard
    req_attr = GuardAttributionRequest(
        sinks=[sample_sink],
        active_guards={"SENDS": "HITL_HUMAN_IN_THE_LOOP"},
    )
    res_attr = service.attribute_guards(req_attr)
    assert len(res_attr.attributions) == 1
    assert res_attr.attributions[0].guard_status == "GUARD_ATTRIBUTED"
    assert res_attr.attributed_count == 1
    assert res_attr.remediation_required is False

    # Test auto repair synthesis when unguarded
    req_repair = AutoRepairPatchRequest(
        sinks=[sample_sink],
        active_guards={},
    )
    res_repair = service.synthesize_auto_repairs(req_repair)
    assert res_repair.total_patches >= 1
    assert any(p.target_sink == "email_sender" for p in res_repair.patches)


def test_kill_switch_lifecycle(service: BlastRadiusInspectorService) -> None:
    # 1. Engage kill switch
    trip_req = ToggleKillSwitchRequest(
        enabled=True,
        reason="Detected rogue exfiltration spike",
        operator="secops_alice",
    )
    status1 = service.toggle_kill_switch(trip_req)
    assert status1.is_engaged is True
    assert status1.reason == "Detected rogue exfiltration spike"
    assert status1.engaged_by == "secops_alice"

    # Query status
    status_query = service.get_kill_switch_status()
    assert status_query.is_engaged is True

    # 2. Disengage kill switch
    reset_req = ToggleKillSwitchRequest(
        enabled=False,
        reason="Incident contained",
        operator="secops_bob",
    )
    status2 = service.toggle_kill_switch(reset_req)
    assert status2.is_engaged is False
    assert status2.reason is None
