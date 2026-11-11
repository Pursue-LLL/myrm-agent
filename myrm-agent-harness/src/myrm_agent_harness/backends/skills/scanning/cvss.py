"""CVSS v3.x base score calculation.

OSV rates an advisory with a CVSS vector string, never with a number, so classifying severity means computing the
base score from the vector's metrics.

[INPUT]
- (none)

[OUTPUT]
- cvss_v3_base_score: base score (0.0-10.0) of a CVSS:3.0 / CVSS:3.1 vector, None for any other vector

[POS]
Severity input for OSV advisories that carry no database-assigned severity label.
"""

from __future__ import annotations

_ATTACK_VECTOR = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
_ATTACK_COMPLEXITY = {"L": 0.77, "H": 0.44}
_PRIVILEGES_REQUIRED = {"N": 0.85, "L": 0.62, "H": 0.27}
_PRIVILEGES_REQUIRED_SCOPE_CHANGED = {"N": 0.85, "L": 0.68, "H": 0.5}
_USER_INTERACTION = {"N": 0.85, "R": 0.62}
_CIA_IMPACT = {"H": 0.56, "L": 0.22, "N": 0.0}
_SCOPE = frozenset({"U", "C"})


def _roundup(value: float) -> float:
    """Smallest number with one decimal that is >= value, immune to binary floating-point noise."""
    scaled = round(value * 100_000)
    if scaled % 10_000 == 0:
        return scaled / 100_000
    return (scaled // 10_000 + 1) / 10.0


def cvss_v3_base_score(vector: str) -> float | None:
    """Return the base score of a CVSS:3.0 / CVSS:3.1 vector, or None when it is another version or malformed."""
    version, _, body = vector.strip().partition("/")
    if version not in ("CVSS:3.0", "CVSS:3.1"):
        return None
    metrics = dict(part.split(":", 1) for part in body.split("/") if ":" in part)

    scope = metrics.get("S")
    if scope not in _SCOPE:
        return None
    scope_changed = scope == "C"
    privileges = _PRIVILEGES_REQUIRED_SCOPE_CHANGED if scope_changed else _PRIVILEGES_REQUIRED
    try:
        exploitability = (
            8.22
            * _ATTACK_VECTOR[metrics["AV"]]
            * _ATTACK_COMPLEXITY[metrics["AC"]]
            * privileges[metrics["PR"]]
            * _USER_INTERACTION[metrics["UI"]]
        )
        impact_sub_score = 1 - (
            (1 - _CIA_IMPACT[metrics["C"]]) * (1 - _CIA_IMPACT[metrics["I"]]) * (1 - _CIA_IMPACT[metrics["A"]])
        )
    except KeyError:
        return None

    if scope_changed:
        impact = 7.52 * (impact_sub_score - 0.029) - 3.25 * (impact_sub_score - 0.02) ** 15
    else:
        impact = 6.42 * impact_sub_score
    if impact <= 0:
        return 0.0
    return _roundup(min((impact + exploitability) * (1.08 if scope_changed else 1.0), 10.0))
