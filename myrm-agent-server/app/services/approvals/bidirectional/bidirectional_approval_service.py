"""[INPUT]
FileDiffPayload, CommandRiskPayload, StructuredApprovalRequest, StructuredApprovalDecision, ApprovalAck from app.services.approvals.bidirectional.protocol_types
[OUTPUT]
BidirectionalApprovalService managing deterministic diff extraction, command risk analysis, and client ACK receipts.
[POS]
app/services/approvals/bidirectional/bidirectional_approval_service.py
"""

import difflib
import re
import time
import uuid
from typing import Optional

from app.services.approvals.bidirectional.protocol_types import (
    ApprovalAck,
    CommandRiskPayload,
    FileDiffPayload,
    RiskSeverity,
    StructuredApprovalDecision,
    StructuredApprovalRequest,
)

_HIGH_RISK_COMMAND_PATTERNS = [
    (re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f*|-rf|-fr)\s+([~/]|\*|\.\.)"), "critical", "Recursive root or wild deletion"),
    (re.compile(r"\bmkfs\b|\bfdisk\b|\bdd\s+if="), "critical", "Raw block device write or disk formatting"),
    (re.compile(r"\b(git\s+reset\s+--hard|git\s+clean\s+-fdx)"), "high", "Destructive git worktree wipe"),
    (re.compile(r"\b(sudo\s+|su\s+root)"), "high", "Elevated root permission privilege escalation"),
    (re.compile(r"\bchmod\s+(-R\s+)?(777|o\+w)"), "high", "Insecure global write permission modification"),
    (re.compile(r"\b(curl|wget)\b.*\|\s*(sh|bash)"), "high", "Piped untrusted remote script execution"),
    (re.compile(r"\brm\s+"), "medium", "File deletion"),
    (re.compile(r"\bkill\s+-9\b|\bpkill\b"), "medium", "Force process termination"),
]


class BidirectionalApprovalService:
    """Service managing bidirectional structured approvals, diff computation, and decision ACKs."""

    def __init__(self) -> None:
        self._pending_requests: dict[str, StructuredApprovalRequest] = {}
        self._decisions: dict[str, StructuredApprovalDecision] = {}
        self._sequence_counter: int = 1

    def compute_file_diff(
        self,
        file_path: str,
        new_content: str,
        old_content: Optional[str] = None,
    ) -> FileDiffPayload:
        """Calculate line-by-line unified diff and line change statistics."""
        old_lines = old_content.splitlines(keepends=True) if old_content is not None else []
        new_lines = new_content.splitlines(keepends=True)

        is_new_file = old_content is None or len(old_lines) == 0
        is_deletion = len(new_lines) == 0 and not is_new_file

        diff_gen = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
        unified_diff_str = "".join(diff_gen)

        added_lines = 0
        removed_lines = 0
        for line in unified_diff_str.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added_lines += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed_lines += 1

        return FileDiffPayload(
            file_path=file_path,
            old_content=old_content,
            new_content=new_content,
            unified_diff=unified_diff_str,
            added_lines=added_lines,
            removed_lines=removed_lines,
            is_new_file=is_new_file,
            is_deletion=is_deletion,
        )

    def analyze_command_risk(self, command: str, cwd: str) -> CommandRiskPayload:
        """Inspect shell command to identify security risks and blast radius."""
        severity: RiskSeverity = "low"
        reasons: list[str] = []
        blast_paths: list[str] = []

        for pattern, risk_level, reason in _HIGH_RISK_COMMAND_PATTERNS:
            match = pattern.search(command)
            if match:
                reasons.append(reason)
                if risk_level == "critical":
                    severity = "critical"
                elif risk_level == "high" and severity != "critical":
                    severity = "high"
                elif risk_level == "medium" and severity in ["low"]:
                    severity = "medium"

                # Extract potential blast radius path
                matched_text = match.group(0)
                blast_paths.append(matched_text.strip())

        if not reasons:
            reasons.append("Standard command execution with no known dangerous patterns detected.")

        return CommandRiskPayload(
            command=command,
            cwd=cwd,
            risk_severity=severity,
            risk_reasons=reasons,
            blast_radius_paths=blast_paths or [cwd],
        )

    def create_file_write_approval(
        self,
        session_id: str,
        file_path: str,
        new_content: str,
        old_content: Optional[str] = None,
        summary: Optional[str] = None,
        timeout_seconds: Optional[float] = 300.0,
    ) -> StructuredApprovalRequest:
        """Create structured approval for file modification or creation."""
        diff_payload = self.compute_file_diff(file_path, new_content, old_content)
        approval_id = f"appr-{uuid.uuid4().hex[:12]}"
        now = time.time()
        expires_at = now + timeout_seconds if timeout_seconds else None

        seq = self._sequence_counter
        self._sequence_counter += 1

        req = StructuredApprovalRequest(
            approval_id=approval_id,
            session_id=session_id,
            sequence_id=seq,
            kind="file_write",
            summary=summary or f"Review code diff for '{file_path}' (+{diff_payload.added_lines} / -{diff_payload.removed_lines})",
            file_diff=diff_payload,
            command_risk=None,
            created_at=now,
            expires_at=expires_at,
            allowed_decisions=["allow", "reject", "remember_session"],
        )
        self._pending_requests[approval_id] = req
        return req

    def create_command_approval(
        self,
        session_id: str,
        command: str,
        cwd: str,
        summary: Optional[str] = None,
        timeout_seconds: Optional[float] = 300.0,
    ) -> StructuredApprovalRequest:
        """Create structured approval for shell command execution."""
        risk_payload = self.analyze_command_risk(command, cwd)
        approval_id = f"appr-{uuid.uuid4().hex[:12]}"
        now = time.time()
        expires_at = now + timeout_seconds if timeout_seconds else None

        seq = self._sequence_counter
        self._sequence_counter += 1

        req = StructuredApprovalRequest(
            approval_id=approval_id,
            session_id=session_id,
            sequence_id=seq,
            kind="command_exec",
            summary=summary or f"Approval required for command [{risk_payload.risk_severity.upper()}]: {command[:60]}",
            file_diff=None,
            command_risk=risk_payload,
            created_at=now,
            expires_at=expires_at,
            allowed_decisions=["allow", "reject", "remember_session"],
        )
        self._pending_requests[approval_id] = req
        return req

    def record_decision(self, decision: StructuredApprovalDecision) -> ApprovalAck:
        """Record decision and issue reliable acknowledgment receipt."""
        approval_id = decision.approval_id
        target_req = self._pending_requests.pop(approval_id, None)

        if not target_req:
            return ApprovalAck(
                approval_id=approval_id,
                sequence_id=0,
                acknowledged=False,
                status="not_found_or_already_resolved",
            )

        self._decisions[approval_id] = decision
        return ApprovalAck(
            approval_id=approval_id,
            sequence_id=target_req.sequence_id,
            acknowledged=True,
            status=f"resolved_{decision.decision}",
        )

    def list_pending_requests(
        self, session_id: Optional[str] = None
    ) -> list[StructuredApprovalRequest]:
        """List active pending approvals, optionally filtered by session ID."""
        now = time.time()
        # Clean expired
        active_requests: list[StructuredApprovalRequest] = []
        for req in list(self._pending_requests.values()):
            if req.expires_at and req.expires_at < now:
                self._pending_requests.pop(req.approval_id, None)
                continue
            if session_id is None or req.session_id == session_id:
                active_requests.append(req)
        return sorted(active_requests, key=lambda r: r.sequence_id)
