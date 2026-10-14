"""Checks that turn a pattern match of a built-in risk rule into a hit.

[INPUT]
- myrm_agent_harness.core.security.detection.pii_patterns::china_id_valid, is_placeholder (POS: Single definition of the built-in PII patterns and their validators: classification, redaction and pseudonymization all read it, so they never disagree about what a hit is.)

[OUTPUT]
- is_confirmed_match: whether the text a built-in rule's pattern matched is a real hit

[POS]
A pattern finds what a value looks like; whether it is one takes the checks the privacy classifier applies to the same
data. Running them here keeps the channel gate and the classifier agreeing about what an ID number, a phone number and an
email address are.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.detection.pii_patterns import china_id_valid, is_placeholder

# Sample values ("user@example.com", "00000000000") are not a person's data.
_REJECTS_PLACEHOLDERS = frozenset({"email_address", "cn_mobile_number"})


def is_confirmed_match(rule_id: str, value: str) -> bool:
    """Whether *value*, which the pattern of the rule *rule_id* matched, is a real hit; a rule without a check always is."""
    if rule_id == "cn_id_card":
        return china_id_valid(value)
    if rule_id in _REJECTS_PLACEHOLDERS:
        return not is_placeholder(value)
    return True
