"""Tests for Dual-Track Prior Audit Server API handlers."""

from myrm_agent_harness.observability.audit_trail import (
    ComplianceOutcome,
    PriorAuditState,
)
from app.api.security.router import (
    export_dual_track_audit,
    get_dual_track_audit_entries,
    get_dual_track_audit_stats,
)
from app.services.security.platform_audit import get_default_audit_collector


def test_dual_track_audit_api_handlers():
    """Verify dual-track audit API query, stats calculation, and export handlers."""
    collector = get_default_audit_collector()
    collector.clear()

    # Pre-act + post-act
    intent = collector.log_intent(
        session_id="sess_server_001",
        agent_id="security_officer",
        tool_name="bash_exec",
        intent_summary="Run vulnerability scanner",
        proposed_args={"scan_target": "localhost", "token": "secret_abc"},
        rule_name="SANDBOX_POLICY",
        is_human_take_the_wheel=True,
    )
    collector.complete_act(intent.entry_id, latency_ms=45.0, output_length=120)

    # Pre-act + refuse
    intent_ref = collector.log_intent(
        session_id="sess_server_001",
        agent_id="security_officer",
        tool_name="rm_file",
        intent_summary="Delete system root",
        proposed_args={"path": "/root"},
        rule_name="CRITICAL_PATH_GUARD",
        is_human_take_the_wheel=False,
    )
    collector.refuse_act(intent_ref.entry_id, reason="Deletion of root blocked")

    # 1. get_dual_track_audit_entries
    import asyncio
    entries = asyncio.run(get_dual_track_audit_entries(session_id="sess_server_001"))
    assert len(entries) == 2
    assert entries[0].rule_name in ("SANDBOX_POLICY", "CRITICAL_PATH_GUARD")

    # 2. get_dual_track_audit_stats
    stats = asyncio.run(get_dual_track_audit_stats(session_id="sess_server_001"))
    assert stats.total_entries == 2
    assert stats.permitted_count == 1
    assert stats.refused_count == 1
    assert stats.human_take_the_wheel_count == 1
    assert stats.compliance_rate == 0.50
    assert len(stats.top_rules_triggered) == 2

    # 3. export_dual_track_audit JSON
    res_json = asyncio.run(export_dual_track_audit(format="json", session_id="sess_server_001"))
    assert res_json.media_type == "application/json"
    assert "SANDBOX_POLICY" in res_json.body.decode("utf-8")

    # 4. export_dual_track_audit CSV
    res_csv = asyncio.run(export_dual_track_audit(format="csv", session_id="sess_server_001"))
    assert res_csv.media_type == "text/csv"
    assert "bash_exec" in res_csv.body.decode("utf-8")

    # 5. export_dual_track_audit Markdown
    res_md = asyncio.run(export_dual_track_audit(format="markdown", session_id="sess_server_001"))
    assert res_md.media_type == "text/markdown"
    assert "Enterprise Compliance" in res_md.body.decode("utf-8")
