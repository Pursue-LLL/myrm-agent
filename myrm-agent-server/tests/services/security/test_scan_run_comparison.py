from __future__ import annotations

from app.schemas.security.scan_comparison import (
    FindingItem,
    ScanRunSummary,
)
from app.services.security.scan_run_comparison import (
    ScanRunComparisonService,
)


def test_finding_item_fingerprint_deterministic() -> None:
    fp1 = FindingItem.compute_fingerprint(
        cwe="CWE-89",
        file_path="src/api/auth.py",
        rule_id="sql-injection-concat",
        signature="cursor.execute(f'SELECT...')",
    )
    fp2 = FindingItem.compute_fingerprint(
        cwe="cwe-89",
        file_path="src/api/auth.py",
        rule_id="sql-injection-concat",
        signature="cursor.execute(f'SELECT...')",
    )
    assert fp1 == fp2
    assert len(fp1) == 16


def test_scan_run_comparison_lifecycle_diff() -> None:
    service = ScanRunComparisonService()

    # 1. Base run with 2 findings
    f1 = FindingItem(
        fingerprint="fp-sql-1",
        rule_id="sql-injection",
        cwe="CWE-89",
        title="SQL Injection in user login",
        severity="critical",
        file_path="app/auth.py",
        poc_verified=True,
    )
    f2 = FindingItem(
        fingerprint="fp-xss-1",
        rule_id="stored-xss",
        cwe="CWE-79",
        title="Stored XSS in comment field",
        severity="medium",
        file_path="app/comments.py",
        poc_verified=False,
    )
    base_run = ScanRunSummary.from_findings(
        run_id="run-001",
        findings=[f1, f2],
        session_id="sess-abc",
        scan_mode="full",
    )
    service.record_run(base_run)

    # Compare base run without parent -> all new
    initial_comp = service.compare_runs(target_run_id="run-001")
    assert len(initial_comp.new_findings) == 2
    assert initial_comp.total_delta == 2

    # 2. Target run: f1 fixed (resolved), f2 still persists, f3 newly introduced
    f3 = FindingItem(
        fingerprint="fp-path-1",
        rule_id="path-traversal",
        cwe="CWE-22",
        title="Path traversal in file download",
        severity="high",
        file_path="app/files.py",
        poc_verified=True,
    )
    target_run = ScanRunSummary.from_findings(
        run_id="run-002",
        findings=[f2, f3],
        session_id="sess-abc",
        scan_mode="diff",
    )
    service.record_run(target_run)

    comparison = service.compare_runs(target_run_id="run-002", base_run_id="run-001")
    assert len(comparison.new_findings) == 1
    assert comparison.new_findings[0].fingerprint == "fp-path-1"
    assert comparison.new_findings[0].status == "new"

    assert len(comparison.persisting_findings) == 1
    assert comparison.persisting_findings[0].fingerprint == "fp-xss-1"
    assert comparison.persisting_findings[0].status == "persisting"

    assert len(comparison.resolved_findings) == 1
    assert comparison.resolved_findings[0].fingerprint == "fp-sql-1"
    assert comparison.resolved_findings[0].status == "resolved"

    assert len(comparison.regressed_findings) == 0
    assert comparison.total_delta == 0  # +1 new - 1 resolved = 0

    # 3. Third run: f1 re-introduced -> should be regressed
    run3 = ScanRunSummary.from_findings(
        run_id="run-003",
        findings=[f1, f2],
        session_id="sess-abc",
        scan_mode="diff",
    )
    service.record_run(run3)
    comp3 = service.compare_runs(target_run_id="run-003", base_run_id="run-002")
    assert len(comp3.regressed_findings) == 1
    assert comp3.regressed_findings[0].fingerprint == "fp-sql-1"
    assert comp3.regressed_findings[0].status == "regressed"


def test_generate_executive_report() -> None:
    service = ScanRunComparisonService()
    f1 = FindingItem(
        fingerprint="fp-sec-1",
        rule_id="hardcoded-secret",
        cwe="CWE-798",
        title="Hardcoded AWS Secret Key",
        severity="critical",
        file_path="config/aws.py",
        poc_verified=True,
        poc_output="Valid AWS STS response returned from token.",
        fix_suggestion="os.environ.get('AWS_SECRET_ACCESS_KEY')",
    )
    run = ScanRunSummary.from_findings(
        run_id="run-exec-1",
        findings=[f1],
        scan_mode="full",
    )
    service.record_run(run)

    report = service.generate_executive_report(run)
    assert "# Executive Security Audit Report" in report
    assert "CWE-798" in report
    assert "Hardcoded AWS Secret Key" in report
    assert "[PoC VERIFIED]" in report
    assert "os.environ.get" in report


def test_scan_run_comparison_persistence(tmp_path: object) -> None:
    from pathlib import Path

    p_file = Path(str(tmp_path)) / "scan_runs.jsonl"
    service1 = ScanRunComparisonService(persistence_path=p_file)

    f1 = FindingItem(
        fingerprint="fp-persist-1",
        rule_id="sqli",
        cwe="CWE-89",
        title="SQL Injection",
        severity="critical",
        file_path="app/auth.py",
        poc_verified=True,
    )
    run1 = ScanRunSummary.from_findings(
        run_id="run-persist-001",
        findings=[f1],
        session_id="session-p1",
        scan_mode="full",
    )
    service1.record_run(run1)

    assert p_file.exists()

    # Create new instance pointing to same file -> should reload run1
    service2 = ScanRunComparisonService(persistence_path=p_file)
    loaded_run = service2.get_run("run-persist-001")
    assert loaded_run is not None
    assert loaded_run.run_id == "run-persist-001"
    assert loaded_run.total_findings == 1
    assert loaded_run.findings[0].fingerprint == "fp-persist-1"
