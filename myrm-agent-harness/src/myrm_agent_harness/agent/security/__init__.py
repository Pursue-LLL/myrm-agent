"""Agent security subsystem — 6-layer onion defense architecture.

[INPUT]
- .types::SecurityConfig, PermissionAction, Capability, PathPolicy (POS: core security types)
- .engine::evaluate_tool_call, check_capability (POS: security evaluation engine)
- .config::parse_security_config (POS: configuration parser)
- .audit::record_decision (POS: security audit logging)

[OUTPUT]
- SecurityConfig, PermissionAction, Capability, PathPolicy, evaluate_tool_call, parse_security_config

[POS]
Agent 安全子系统入口。提供 6 层洋葱防御架构的类型、引擎、配置与审计日志统一门面导出。
"""

from importlib import import_module as _import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .audit import SecurityDecision, get_audit_entries, record_decision, reset_audit_log
    from .batch_risk import (
        BatchApprovalItem,
        BatchItemRiskLevel,
        BatchRiskItemDetail,
        BatchRiskReport,
        classify_batch_approval_risk,
    )
    from .config import from_config, parse_security_config
    from .detection.pseudonym_store import PseudonymStore, get_pseudonym_store
    from .detection.pseudonymizer import PIIItem, PseudonymRestorer, pseudonymize_text
    from .engine import check_capability, disabled_permissions, evaluate, evaluate_tool_call, extract_url_domains, merge
    from .guards.privacy_tracker import get_pending_privacy_event, get_privacy_tracker, reset_privacy_tracker
    from .message_filtering import FilterConfig, FilterContext, MessageFilter, MessageFilterPipeline, SystemRoleFilter
    from .redact import RedactingFormatter, redact_sensitive_text
    from .script_operand_verifier import (
        compute_file_content_digest,
        extract_script_file_operand,
        verify_script_operand_integrity,
    )
    from .single_use_tickets import (
        SingleUseTicket,
        SingleUseTicketManager,
        TicketStatus,
        TokenType,
        compute_content_digest,
        get_single_use_ticket_manager,
    )
    from .team_identity import (
        CredentialTrack,
        TeamIdentityScope,
        TeamIdentitySpec,
        credential_track_for,
        memory_namespace_for,
        sanitize_identity_id,
    )
    from .transcript_classifier import TranscriptClassifier
    from .types import (
        DEFAULT_CAPABILITIES,
        DEFAULT_RULESET,
        Capability,
        CapabilitySet,
        EphemeralUserCredential,
        PathPolicy,
        PermissionAction,
        PermissionRule,
        PermissionRuleset,
        PIIAction,
        PrivacyPolicy,
        RecentToolCall,
        ReviewDecision,
        ReviewResult,
        SecurityConfig,
        SecurityReviewerProtocol,
        SensitivityLevel,
        user_credentials_ctx,
    )

_EXPORTS: dict[str, tuple[str, str]] = {
    # types.py
    "Capability": (".types", "Capability"),
    "CapabilitySet": (".types", "CapabilitySet"),
    "DEFAULT_CAPABILITIES": (".types", "DEFAULT_CAPABILITIES"),
    "PermissionAction": (".types", "PermissionAction"),
    "PermissionRule": (".types", "PermissionRule"),
    "PermissionRuleset": (".types", "PermissionRuleset"),
    "DEFAULT_RULESET": (".types", "DEFAULT_RULESET"),
    "PathPolicy": (".types", "PathPolicy"),
    "SecurityConfig": (".types", "SecurityConfig"),
    "SensitivityLevel": (".types", "SensitivityLevel"),
    "PIIAction": (".types", "PIIAction"),
    "PrivacyPolicy": (".types", "PrivacyPolicy"),
    "ReviewDecision": (".types", "ReviewDecision"),
    "ReviewResult": (".types", "ReviewResult"),
    "RecentToolCall": (".types", "RecentToolCall"),
    "SecurityReviewerProtocol": (".types", "SecurityReviewerProtocol"),
    "EphemeralUserCredential": (".types", "EphemeralUserCredential"),
    "user_credentials_ctx": (".types", "user_credentials_ctx"),
    # transcript_classifier.py
    "TranscriptClassifier": (".transcript_classifier", "TranscriptClassifier"),
    # guards/privacy_tracker.py
    "get_privacy_tracker": (".guards.privacy_tracker", "get_privacy_tracker"),
    "reset_privacy_tracker": (".guards.privacy_tracker", "reset_privacy_tracker"),
    "get_pending_privacy_event": (".guards.privacy_tracker", "get_pending_privacy_event"),
    # engine.py
    "evaluate": (".engine", "evaluate"),
    "evaluate_tool_call": (".engine", "evaluate_tool_call"),
    "check_capability": (".engine", "check_capability"),
    "merge": (".engine", "merge"),
    "disabled_permissions": (".engine", "disabled_permissions"),
    "extract_url_domains": (".engine", "extract_url_domains"),
    # config.py
    "parse_security_config": (".config", "parse_security_config"),
    "from_config": (".config", "from_config"),
    # audit.py
    "record_decision": (".audit", "record_decision"),
    "get_audit_entries": (".audit", "get_audit_entries"),
    "reset_audit_log": (".audit", "reset_audit_log"),
    "SecurityDecision": (".audit", "SecurityDecision"),
    # redact.py
    "redact_sensitive_text": (".redact", "redact_sensitive_text"),
    "RedactingFormatter": (".redact", "RedactingFormatter"),
    # detection/pseudonym_store.py
    "PseudonymStore": (".detection.pseudonym_store", "PseudonymStore"),
    "get_pseudonym_store": (".detection.pseudonym_store", "get_pseudonym_store"),
    # detection/pseudonymizer.py
    "pseudonymize_text": (".detection.pseudonymizer", "pseudonymize_text"),
    "PseudonymRestorer": (".detection.pseudonymizer", "PseudonymRestorer"),
    "PIIItem": (".detection.pseudonymizer", "PIIItem"),
    # message_filtering
    "FilterConfig": (".message_filtering", "FilterConfig"),
    "FilterContext": (".message_filtering", "FilterContext"),
    "MessageFilter": (".message_filtering", "MessageFilter"),
    "MessageFilterPipeline": (".message_filtering", "MessageFilterPipeline"),
    "SystemRoleFilter": (".message_filtering", "SystemRoleFilter"),
    # batch_risk.py
    "BatchApprovalItem": (".batch_risk", "BatchApprovalItem"),
    "BatchItemRiskLevel": (".batch_risk", "BatchItemRiskLevel"),
    "BatchRiskItemDetail": (".batch_risk", "BatchRiskItemDetail"),
    "BatchRiskReport": (".batch_risk", "BatchRiskReport"),
    "classify_batch_approval_risk": (".batch_risk", "classify_batch_approval_risk"),
    # script_operand_verifier.py
    "extract_script_file_operand": (".script_operand_verifier", "extract_script_file_operand"),
    "compute_file_content_digest": (".script_operand_verifier", "compute_file_content_digest"),
    "verify_script_operand_integrity": (".script_operand_verifier", "verify_script_operand_integrity"),
    # team_identity.py
    "TeamIdentityScope": (".team_identity", "TeamIdentityScope"),
    "CredentialTrack": (".team_identity", "CredentialTrack"),
    "TeamIdentitySpec": (".team_identity", "TeamIdentitySpec"),
    "memory_namespace_for": (".team_identity", "memory_namespace_for"),
    "credential_track_for": (".team_identity", "credential_track_for"),
    "sanitize_identity_id": (".team_identity", "sanitize_identity_id"),
    # single_use_tickets
    "SingleUseTicket": (".single_use_tickets", "SingleUseTicket"),
    "SingleUseTicketManager": (".single_use_tickets", "SingleUseTicketManager"),
    "TicketStatus": (".single_use_tickets", "TicketStatus"),
    "TokenType": (".single_use_tickets", "TokenType"),
    "compute_content_digest": (".single_use_tickets", "compute_content_digest"),
    "get_single_use_ticket_manager": (".single_use_tickets", "get_single_use_ticket_manager"),
}

__all__ = [
    "BatchApprovalItem",
    "BatchItemRiskLevel",
    "BatchRiskItemDetail",
    "BatchRiskReport",
    "Capability",
    "CapabilitySet",
    "CredentialTrack",
    "DEFAULT_CAPABILITIES",
    "DEFAULT_RULESET",
    "EphemeralUserCredential",
    "FilterConfig",
    "FilterContext",
    "MessageFilter",
    "MessageFilterPipeline",
    "PIIAction",
    "PIIItem",
    "PathPolicy",
    "PermissionAction",
    "PermissionRule",
    "PermissionRuleset",
    "PrivacyPolicy",
    "PseudonymRestorer",
    "PseudonymStore",
    "RecentToolCall",
    "RedactingFormatter",
    "ReviewDecision",
    "ReviewResult",
    "SecurityConfig",
    "SecurityDecision",
    "SecurityReviewerProtocol",
    "SensitivityLevel",
    "SingleUseTicket",
    "SingleUseTicketManager",
    "SystemRoleFilter",
    "TeamIdentityScope",
    "TeamIdentitySpec",
    "TicketStatus",
    "TokenType",
    "TranscriptClassifier",
    "check_capability",
    "classify_batch_approval_risk",
    "compute_content_digest",
    "compute_file_content_digest",
    "credential_track_for",
    "disabled_permissions",
    "evaluate",
    "evaluate_tool_call",
    "extract_script_file_operand",
    "extract_url_domains",
    "from_config",
    "get_audit_entries",
    "get_pending_privacy_event",
    "get_privacy_tracker",
    "get_pseudonym_store",
    "get_single_use_ticket_manager",
    "memory_namespace_for",
    "merge",
    "parse_security_config",
    "pseudonymize_text",
    "record_decision",
    "redact_sensitive_text",
    "reset_audit_log",
    "reset_privacy_tracker",
    "sanitize_identity_id",
    "user_credentials_ctx",
    "verify_script_operand_integrity",
]


def __getattr__(name: str) -> object:
    spec = _EXPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_path, attr_name = spec
    module = _import_module(module_path, __name__)
    return getattr(module, attr_name)


def __dir__() -> list[str]:
    public = set(__all__)
    public.update(k for k in globals() if not k.startswith("_"))
    public.discard("_import_module")
    return sorted(public)
