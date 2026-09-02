"""Security vulnerability scan run comparison and lifecycle tracking service.

[INPUT]
- app.schemas.security.scan_comparison::(FindingItem, ScanRunSummary, ScanComparisonResult) (POS: Schema DTOs)

[OUTPUT]
- ScanRunComparisonService: Service managing scan runs, state machine diffs, and executive reports.

[POS]
Provides core state machine and lifecycle comparison (New / Persisting / Resolved / Regressed)
for agentic code security scans in the server layer.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.schemas.security.scan_comparison import (
    FindingItem,
    ScanComparisonResult,
    ScanRunSummary,
)

logger = logging.getLogger(__name__)


class ScanRunComparisonService:
    """Service tracking security scan runs and computing deterministic finding diffs."""

    def __init__(self, persistence_path: str | Path | None = None) -> None:
        self._runs: dict[str, ScanRunSummary] = {}
        self._resolved_history: set[str] = set()
        self._persistence_path: Path | None = (
            Path(persistence_path) if persistence_path else None
        )
        if self._persistence_path:
            self._load_persisted_runs()

    def _load_persisted_runs(self) -> None:
        """Load historical runs from JSONL persistence file if exists."""
        if not self._persistence_path or not self._persistence_path.exists():
            return
        try:
            with open(self._persistence_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    data = json.loads(line_str)
                    run = ScanRunSummary.model_validate(data)
                    self._runs[run.run_id] = run
        except Exception as exc:
            logger.warning(
                "Failed to load persisted scan runs from %s: %s",
                self._persistence_path,
                exc,
            )

    def record_run(self, run: ScanRunSummary) -> ScanRunSummary:
        """Store a scan run snapshot in memory/store and append to persistence."""
        self._runs[run.run_id] = run
        if self._persistence_path:
            try:
                self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._persistence_path, "a", encoding="utf-8") as f:
                    f.write(run.model_dump_json() + "\n")
            except Exception as exc:
                logger.warning(
                    "Failed to persist scan run %s to %s: %s",
                    run.run_id,
                    self._persistence_path,
                    exc,
                )
        return run

    def get_run(self, run_id: str) -> ScanRunSummary | None:
        """Retrieve a scan run by run_id."""
        return self._runs.get(run_id)

    def list_runs(
        self, session_id: str | None = None, limit: int = 20
    ) -> list[ScanRunSummary]:
        """List scan runs sorted by created_at descending."""
        runs = list(self._runs.values())
        if session_id:
            runs = [r for r in runs if r.session_id == session_id]
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs[:limit]

    def compare_runs(
        self,
        target_run_id: str,
        base_run_id: str | None = None,
    ) -> ScanComparisonResult:
        """Compute state machine diff between target run and baseline run."""
        target_run = self.get_run(target_run_id)
        if not target_run:
            raise ValueError(f"Target run {target_run_id} not found.")

        if not base_run_id:
            # Baseline is empty: all findings in target are new
            new_items: list[FindingItem] = []
            for f in target_run.findings:
                copy_item = f.model_copy()
                copy_item.status = "new"
                new_items.append(copy_item)

            return ScanComparisonResult(
                base_run_id=None,
                target_run_id=target_run_id,
                new_findings=new_items,
                persisting_findings=[],
                resolved_findings=[],
                regressed_findings=[],
                total_delta=len(new_items),
                summary_text=f"Initial scan completed with {len(new_items)} active findings.",
            )

        base_run = self.get_run(base_run_id)
        if not base_run:
            raise ValueError(f"Base run {base_run_id} not found.")

        base_map: dict[str, FindingItem] = {f.fingerprint: f for f in base_run.findings}
        target_map: dict[str, FindingItem] = {
            f.fingerprint: f for f in target_run.findings
        }

        new_findings: list[FindingItem] = []
        persisting_findings: list[FindingItem] = []
        regressed_findings: list[FindingItem] = []
        resolved_findings: list[FindingItem] = []

        # Process target findings
        for fp, target_item in target_map.items():
            if fp in base_map:
                item = target_item.model_copy()
                item.status = "persisting"
                persisting_findings.append(item)
            elif fp in self._resolved_history:
                item = target_item.model_copy()
                item.status = "regressed"
                regressed_findings.append(item)
            else:
                item = target_item.model_copy()
                item.status = "new"
                new_findings.append(item)

        # Process resolved findings (in base but absent in target)
        for fp, base_item in base_map.items():
            if fp not in target_map:
                item = base_item.model_copy()
                item.status = "resolved"
                resolved_findings.append(item)
                self._resolved_history.add(fp)

        total_delta = (len(new_findings) + len(regressed_findings)) - len(
            resolved_findings
        )
        summary = (
            f"Comparison with {base_run_id}: "
            f"+{len(new_findings)} new, +{len(regressed_findings)} regressed, "
            f"-{len(resolved_findings)} resolved, {len(persisting_findings)} persisting."
        )

        return ScanComparisonResult(
            base_run_id=base_run_id,
            target_run_id=target_run_id,
            new_findings=new_findings,
            persisting_findings=persisting_findings,
            resolved_findings=resolved_findings,
            regressed_findings=regressed_findings,
            total_delta=total_delta,
            summary_text=summary,
        )

    def generate_executive_report(
        self,
        run: ScanRunSummary,
        comparison: ScanComparisonResult | None = None,
    ) -> str:
        """Generate structured executive markdown report for security findings."""
        timestamp_str = run.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        report_lines: list[str] = [
            "# Executive Security Audit Report",
            "",
            f"- **Run ID**: `{run.run_id}`",
            f"- **Scan Mode**: `{run.scan_mode.upper()}`",
            f"- **Generated At**: {timestamp_str}",
            f"- **Total Findings**: {run.total_findings} (Critical: {run.critical_count}, High: {run.high_count}, Verified PoC: {run.poc_verified_count})",
            "",
        ]

        if comparison:
            report_lines.extend(
                [
                    f"## Comparison Summary vs Baseline (`{comparison.base_run_id or 'None'}`)",
                    "",
                    f"> {comparison.summary_text}",
                    "",
                    f"- **New Findings**: {len(comparison.new_findings)}",
                    f"- **Resolved Findings**: {len(comparison.resolved_findings)}",
                    f"- **Regressed Findings**: {len(comparison.regressed_findings)}",
                    f"- **Persisting Findings**: {len(comparison.persisting_findings)}",
                    "",
                ]
            )

        report_lines.extend(
            [
                "## Detailed Findings",
                "",
            ]
        )

        if not run.findings:
            report_lines.append(
                "✅ No security vulnerabilities detected in the target scope.\n"
            )
        else:
            for idx, finding in enumerate(run.findings, 1):
                poc_badge = (
                    "🛡️ **[PoC VERIFIED]**"
                    if finding.poc_verified
                    else "⚠️ [STATIC INFERENCE]"
                )
                report_lines.extend(
                    [
                        f"### {idx}. [{finding.severity.upper()}] {finding.title} ({finding.cwe})",
                        f"- **Status**: `{finding.status.upper()}` · **Fingerprint**: `{finding.fingerprint}`",
                        f"- **Location**: `{finding.file_path}`"
                        + (
                            f" (Lines: `{finding.line_range}`)"
                            if finding.line_range
                            else ""
                        ),
                        f"- **Verification**: {poc_badge}",
                    ]
                )
                if finding.poc_output:
                    report_lines.extend(
                        [
                            "- **PoC Proof Output**:",
                            "  ```text",
                            f"  {finding.poc_output.strip()}",
                            "  ```",
                        ]
                    )
                if finding.fix_suggestion:
                    report_lines.extend(
                        [
                            "- **Remediation Suggestion**:",
                            "  ```python",
                            f"  {finding.fix_suggestion.strip()}",
                            "  ```",
                        ]
                    )
                report_lines.append("")

        return "\n".join(report_lines)
