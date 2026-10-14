"""Risk rule vocabulary: severity, action, category, and which categories start enabled.

Severity levels: low / medium / high
Action: block (a rule that should not apply is disabled, not given another action)
Categories: personal / company / security / finance_legal / political / customer
"""

from __future__ import annotations

# The seed definition of a built-in rule: ``rule_id``, ``display_name``, ``description``, ``pattern``, ``severity``,
# ``action``, ``category`` and ``sort_order``.
RuleSeed = dict[str, str | int | bool]


class RiskSeverity:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    RANK = {LOW: 1, MEDIUM: 2, HIGH: 3}


class RiskAction:
    BLOCK = "block"


class RiskCategory:
    PERSONAL = "personal"
    COMPANY = "company"
    SECURITY = "security"
    FINANCE_LEGAL = "finance_legal"
    POLITICAL = "political"
    CUSTOMER = "customer"
    CUSTOM = "custom"


# Built-in rules of these categories start enabled. Credentials are never something a message needs to carry, so they
# are held from the first message; the other categories (names, contracts, budgets, e-mail addresses) are everyday
# subjects of a personal assistant, so the user turns them on when their own data calls for it.
DEFAULT_ENABLED_CATEGORIES = frozenset({RiskCategory.SECURITY})
