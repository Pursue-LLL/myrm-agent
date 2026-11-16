"""Which rules of an import are new to the manager.

[INPUT]
- memory.types::ProceduralMemory (POS: the rule whose identity is compared)

[OUTPUT]
- rule_identity: what makes two rules the same rule
- without_known_rules: the rules of an import minus those already stored or repeated within the import

[POS]
Stateless half of the rule import's deduplication; the store-facing half reads the stored rules in ``mixin``.
A rule has no natural key and the writer never deduplicates one, so ``import_memories`` drops what it already holds
before writing. Two rules are the same when they apply under the same condition, ask for the same thing and are scoped
to the same tool; spacing and letter case do not make a rule another rule.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from myrm_agent_harness.toolkits.memory.types import ProceduralMemory


def _reading(text: str) -> str:
    return " ".join(text.split()).casefold()


def rule_identity(rule: ProceduralMemory) -> tuple[str, str, str]:
    """The trigger, the action and the tool a rule is scoped to (empty for a global rule)."""
    return (_reading(rule.trigger), _reading(rule.action), rule.tool_name or "")


def without_known_rules(rules: Sequence[ProceduralMemory], known: Iterable[ProceduralMemory]) -> list[ProceduralMemory]:
    """``rules`` minus the ones ``known`` already holds and the ones that repeat an earlier entry of ``rules``."""
    seen = {rule_identity(rule) for rule in known}
    fresh: list[ProceduralMemory] = []
    for rule in rules:
        identity = rule_identity(rule)
        if identity not in seen:
            seen.add(identity)
            fresh.append(rule)
    return fresh
