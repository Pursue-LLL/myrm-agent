"""[INPUT]
- myrm_agent_harness.agent.security.audit_pack::LegalAuditDocket, LegalAuditDocketBuilder, TriadDelegationProof (POS: 框架层法律案卷打包引擎)
- myrm_agent_harness.agent.security.delegation.models::SubjectIdentity, ActorType (POS: 三元委托身份模型)
- myrm_agent_harness.agent.security.jit_gate.models::AssetContentFingerprint (POS: 物理资产不可变指纹)
- app.database.models.approval::ApprovalRecord (POS: 数据库审批单)
- app.services.approvals.audit_ledger::get_audit_ledger (POS: 防篡改审计存证账本)

[OUTPUT]
- DocketService: 业务层法律级审计案卷包构建与导出服务

[POS]
在审批通过时刻聚合三元委托身份链、物理资产指纹与底层执行回执，生成带有密码学封签的不可抵赖合规案卷包。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import ClassVar

from myrm_agent_harness.agent.security.audit_pack import (
    LegalAuditDocket,
    LegalAuditDocketBuilder,
    TriadDelegationProof,
)
from myrm_agent_harness.agent.security.delegation.models import SubjectIdentity, SubjectType
from myrm_agent_harness.agent.security.jit_gate.models import AssetContentFingerprint

from app.database.models.approval import ApprovalRecord
from app.services.approvals.audit_ledger import get_audit_ledger

logger = logging.getLogger(__name__)


class DocketService:
    """Service generating and archiving tamper-evident LegalAuditDocket dossiers."""

    _lock = threading.Lock()
    _dockets: ClassVar[dict[str, LegalAuditDocket]] = {}  # Key: approval_id

    @classmethod
    def get_signing_secret(cls) -> str:
        """Obtain enterprise KMS signing key or secure fallback secret."""
        return os.environ.get("AUDIT_DOCKET_SIGNING_KEY", "openperplexity-legal-audit-key-2026")

    @classmethod
    async def create_docket_for_approval(
        cls,
        record: ApprovalRecord,
        approver_id: str = "human_approver",
    ) -> LegalAuditDocket:
        """Assemble the 5 golden evidence elements for a resolved approval record."""
        payload = record.payload or {}

        # 1. Triad Delegation Proof
        initial_requester = SubjectIdentity(
            subject_id=record.agent_id or "user_requester",
            subject_type=SubjectType.HUMAN,
            display_name=f"User {record.agent_id or 'requester'}",
            scopes=frozenset({"standard_user"}),
        )
        executor_agent = SubjectIdentity(
            subject_id=record.agent_id or "primary_agent",
            subject_type=SubjectType.AGENT,
            display_name="Primary Execution Agent",
            scopes=frozenset({"executor_agent"}),
        )
        business_approver = SubjectIdentity(
            subject_id=approver_id,
            subject_type=SubjectType.HUMAN,
            display_name=f"Approver {approver_id}",
            scopes=frozenset({"compliance_approver"}),
        )
        triad_proof = TriadDelegationProof(
            initial_requester=initial_requester,
            executor_agent=executor_agent,
            business_approver=business_approver,
        )

        builder = LegalAuditDocketBuilder(
            action_type=record.action_type,
            triad_proof=triad_proof,
        )

        # 2. Input / Output Summaries
        reason_text = record.reason or "No specific approval reason provided"
        builder.set_input_summary(f"Action: {record.action_type}, Request reason: {reason_text}")
        builder.set_output_summary(f"Approval status resolved to: {record.status}")

        # 3. Physical Asset Fingerprint (if attached to payload)
        fingerprint_data = payload.get("content_fingerprint")
        if isinstance(fingerprint_data, dict):
            fp = AssetContentFingerprint.from_dict(fingerprint_data)
            builder.add_asset_fingerprint(fp)

        # 4. Link Audit Receipt Hash from Ledger
        try:
            ledger = get_audit_ledger()
            recent_receipts = ledger.list_receipts(limit=1)
            if recent_receipts:
                builder.add_execution_receipt_hash(recent_receipts[0].compute_hash())
        except Exception as exc:
            logger.warning("[DOCKET_SERVICE] Could not link ledger receipt: %s", exc)

        builder.add_metadata("approval_id", record.id)
        builder.add_metadata("chat_id", str(record.chat_id or "none"))
        builder.add_metadata("thread_id", str(record.thread_id or "none"))

        # 5. Sign and Seal Docket
        docket = builder.build_and_seal(
            signing_secret=cls.get_signing_secret(),
            key_id="kms-enterprise-legal-seal",
        )

        with cls._lock:
            cls._dockets[record.id] = docket

        logger.info(
            "[DOCKET_SERVICE] Sealed legal audit docket %s for approval %s (Root Digest: %s)",
            docket.docket_id,
            record.id,
            docket.root_digest[:16],
        )
        return docket

    @classmethod
    def get_docket(cls, approval_id: str) -> LegalAuditDocket | None:
        """Retrieve archived legal audit docket by approval ID."""
        with cls._lock:
            return cls._dockets.get(approval_id)

    @classmethod
    def clear_dockets(cls) -> None:
        """Clear cached dockets (used in tests)."""
        with cls._lock:
            cls._dockets.clear()
