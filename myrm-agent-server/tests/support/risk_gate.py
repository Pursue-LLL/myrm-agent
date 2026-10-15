"""A detection service with injected rules, for tests that exercise a risk gate without the stored built-in rules."""

from __future__ import annotations

from app.services.risk.detection import RiskDetectionService, _CompiledRule, compile_pattern

SECRET = "sk-AAAAAABBBBBBCCCCCCDDDD"

API_KEY_RULE = _CompiledRule(
    rule_id="r-apikey",
    display_name="API Key Leak",
    severity="critical",
    category="credential",
    compiled=compile_pattern(r"sk-[A-Za-z0-9]{20,}"),
)

PHONE_RULE = _CompiledRule(
    rule_id="r-phone",
    display_name="CN Mobile",
    severity="high",
    category="pii",
    compiled=compile_pattern(r"1[3-9]\d{9}"),
)


def build_service_with_rules(rules: list[_CompiledRule]) -> RiskDetectionService:
    service = RiskDetectionService()
    service._rules = rules
    service._version = 1
    return service
