"""Compares the verdicts of a replay with the recorded ones and explains each difference by a registered reason.

[INPUT]
- (none: plain verdict mappings)

[OUTPUT]
- Verdict: what one case came to, as a flat mapping of named facts
- Allowed: one intended difference, the facts that changed with their new values and why the new verdict is right
- Report / compare: the differences no entry explains and the entries that explain nothing

[POS]
Engine of the golden failure and answer tests. A difference is explained only by an entry that names the case and
states exactly what changed, so a regression cannot hide behind an entry written for another change of the same case;
an entry for a case that no longer differs is reported as stale, so the registry cannot outlive what it explains.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

Verdict = dict[str, object]


@dataclass(frozen=True, slots=True)
class Allowed:
    new: Mapping[str, object]
    why: str


@dataclass(frozen=True, slots=True)
class Report:
    unexplained: dict[str, tuple[Verdict, Verdict]]
    stale: list[str]

    def describe(self) -> str:
        return "\n".join(
            f"{case}\n  recorded {old}\n  replayed {new}" for case, (old, new) in sorted(self.unexplained.items())
        )


def changed(recorded: Verdict, replayed: Verdict) -> dict[str, object]:
    """The facts that differ, each with its replayed value (``None`` for a fact the replay no longer states)."""
    return {
        fact: replayed.get(fact)
        for fact in recorded.keys() | replayed.keys()
        if recorded.get(fact) != replayed.get(fact)
    }


def compare(recorded: Mapping[str, Verdict], replayed: Mapping[str, Verdict], allowed: Mapping[str, Allowed]) -> Report:
    """Differences between the two verdict sets that ``allowed`` does not explain exactly, and entries that explain none."""
    assert set(replayed) == set(recorded), "the replay and the recording cover different cases"
    assert set(allowed) <= set(recorded), f"registered cases that were never recorded: {set(allowed) - set(recorded)}"
    unexplained: dict[str, tuple[Verdict, Verdict]] = {}
    for case, old in recorded.items():
        difference = changed(old, replayed[case])
        entry = allowed.get(case)
        if difference and (entry is None or dict(entry.new) != difference):
            unexplained[case] = (old, replayed[case])
    stale = sorted(case for case in allowed if not changed(recorded[case], replayed[case]))
    return Report(unexplained, stale)
