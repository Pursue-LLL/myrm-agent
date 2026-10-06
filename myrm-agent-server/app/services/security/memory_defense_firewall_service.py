"""Service layer for Memory Defense Ingestion Firewall and PII Sanitization Suite.

[INPUT]
- myrm_agent_harness.core.security.memory_defense_firewall::MemoryDefenseFirewall, DefenseAction
- app.schemas.memory_defense_firewall::DefenseInspectRequest, ExemptionAddRequest

[OUTPUT]
- MemoryDefenseFirewallService, get_memory_defense_firewall_service

[POS]
Business service managing memory defense ingestion firewall, sensitive PII redaction, and exemptions.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.memory_defense_firewall import (
    DefenseAction,
    DefensePolicy,
    DetectionMatch,
    MemoryDefenseFirewall,
    MemoryDefenseResult,
    PatternSpec,
    SensitiveCategory,
    get_builtin_patterns,
)

from app.schemas.memory_defense_firewall import (
    DefenseInspectRequest,
    DefenseInspectResponse,
    DetectionMatchItem,
    ExemptionListResponse,
    ExemptionResponse,
    PatternCatalogItem,
    PatternCatalogResponse,
)

logger = logging.getLogger(__name__)


def _to_match_item(m: DetectionMatch) -> DetectionMatchItem:
    return DetectionMatchItem(
        pattern_id=m.pattern_id,
        pattern_name=m.pattern_name,
        category=m.category.value,
        start=m.start,
        end=m.end,
        matched_preview=m.matched_preview,
        replacement_tag=m.replacement_tag,
    )


def _to_inspect_response(res: MemoryDefenseResult) -> DefenseInspectResponse:
    return DefenseInspectResponse(
        action_taken=res.action_taken.value,
        is_admitted=res.is_admitted,
        sanitized_text=res.sanitized_text,
        original_length=res.original_length,
        sanitized_length=res.sanitized_length,
        matches=[_to_match_item(m) for m in res.matches],
        audit_id=res.audit_id,
        timestamp=res.timestamp,
    )


def _to_pattern_catalog_item(p: PatternSpec) -> PatternCatalogItem:
    return PatternCatalogItem(
        pattern_id=p.pattern_id,
        name=p.name,
        category=p.category.value,
        replacement_tag=p.replacement_tag,
        description=p.description,
    )


class MemoryDefenseFirewallService:
    """Manages pre-ingestion memory defense, sensitive redaction, and whitelist exemptions."""

    def __init__(self, firewall: MemoryDefenseFirewall | None = None) -> None:
        self._firewall = firewall or MemoryDefenseFirewall()

    @property
    def firewall(self) -> MemoryDefenseFirewall:
        return self._firewall

    def inspect_and_defend(self, req: DefenseInspectRequest) -> DefenseInspectResponse:
        """Inspect inbound text and apply ALLOW, REDACT, or BLOCK action."""
        default_act = DefenseAction.REDACT
        try:
            default_act = DefenseAction(req.default_action.upper())
        except ValueError:
            default_act = DefenseAction.REDACT

        blocked_cats: set[SensitiveCategory] = set()
        for cat_str in req.blocked_categories:
            try:
                blocked_cats.add(SensitiveCategory(cat_str.upper()))
            except ValueError:
                continue

        policy = DefensePolicy(
            default_action=default_act,
            blocked_categories=blocked_cats,
        )

        res = self._firewall.inspect_and_defend(req.text, policy=policy)
        logger.info(
            "Memory defense evaluated text: action=%s, admitted=%s, matches=%d, audit_id=%s",
            res.action_taken.value,
            res.is_admitted,
            len(res.matches),
            res.audit_id,
        )
        return _to_inspect_response(res)

    def add_exemption(self, token_or_content: str) -> ExemptionResponse:
        """Add false-positive token or content hash to exemption whitelist."""
        self._firewall.add_exemption(token_or_content)
        return ExemptionResponse(success=True, token_or_content=token_or_content)

    def remove_exemption(self, token_or_content: str) -> ExemptionResponse:
        """Remove false-positive entry from exemption whitelist."""
        existed = self._firewall.remove_exemption(token_or_content)
        return ExemptionResponse(success=existed, token_or_content=token_or_content)

    def list_exemptions(self) -> ExemptionListResponse:
        """List active exemption whitelist tokens and fingerprints."""
        entries = self._firewall.list_exemptions()
        return ExemptionListResponse(exemptions=entries)

    def get_pattern_catalog(self) -> PatternCatalogResponse:
        """Retrieve full catalog of supported sensitive detection patterns."""
        specs = get_builtin_patterns()
        items = [_to_pattern_catalog_item(p) for p in specs]
        return PatternCatalogResponse(total_count=len(items), patterns=items)

    def get_audit_records(self, limit: int = 50) -> list[DefenseInspectResponse]:
        """Fetch historical audit evaluation entries."""
        records = self._firewall.get_audit_records(limit=limit)
        return [_to_inspect_response(r) for r in records]


_service_instance: MemoryDefenseFirewallService | None = None


def get_memory_defense_firewall_service() -> MemoryDefenseFirewallService:
    """Singleton getter for MemoryDefenseFirewallService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = MemoryDefenseFirewallService()
    return _service_instance
