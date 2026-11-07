"""Structural diff of two request captures and the registry check that explains every difference.

[INPUT]
- golden_allowed / golden_bedrock_allowed (POS: the registries of intentional differences)
- golden_allowed_types (POS: AllowedDiff and the URLs the previous library fetched on its own)

[OUTPUT]
- Diff / diff_request / diff_case: the differences between a baseline and a current request
- CHAT_RULES: every registered difference of the chat requests
- explain: split differences into registered ones and unexplained ones

[POS]
Engine of the golden request test. A difference is explained only by a registered rule that names the provider,
the kind of change and the field, so an unintended change to any request field fails the test.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from .golden_allowed import RULES
from .golden_allowed_types import HIDDEN_FETCHES, AllowedDiff
from .golden_bedrock_allowed import BEDROCK_RULES

CHAT_RULES: tuple[AllowedDiff, ...] = (*RULES, *BEDROCK_RULES)
_VOLATILE_HEADERS = frozenset({"user-agent", "content-type"})


@dataclass(frozen=True, slots=True)
class Diff:
    kind: str  # "+" field only in the current request, "-" only in the baseline, "~" value changed, "count"
    path: str
    old: object
    new: object


def _walk(old: object, new: object, path: str = "") -> Iterator[Diff]:
    if isinstance(old, Mapping) and isinstance(new, Mapping):
        for key in sorted(set(old) | set(new)):
            if key not in old:
                yield Diff("+", f"{path}/{key}", None, new[key])
            elif key not in new:
                yield Diff("-", f"{path}/{key}", old[key], None)
            else:
                yield from _walk(old[key], new[key], f"{path}/{key}")
    elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for index, (a, b) in enumerate(zip(old, new, strict=True)):
            yield from _walk(a, b, f"{path}[{index}]")
    elif old != new:
        yield Diff("~", path, old, new)


def _camel(key: str) -> str:
    head, *rest = key.split("_")
    return head + "".join(part.title() for part in rest)


def _camel_keys(value: object) -> object:
    if isinstance(value, Mapping):
        return {_camel(str(k)): _camel_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_camel_keys(v) for v in value]
    return value


def _canonical_contents(turns: object) -> object:
    """Gemini turns in the one form the API treats alike: no empty text part, one turn per run of a role.

    Compared this way a Gemini request still differs on every field that matters (ids, signatures, arguments, text),
    without a rule per spelling of the same turn.
    """
    if not isinstance(turns, list):
        return turns
    merged: list[dict[str, object]] = []
    for turn in turns:
        parts = [p for p in turn.get("parts", []) if p != {"text": ""}]
        if merged and merged[-1]["role"] == turn.get("role"):
            merged[-1]["parts"] = [*merged[-1]["parts"], *parts]  # type: ignore[misc]
        else:
            merged.append({**turn, "parts": parts})
    return merged


def _comparable(request: Mapping[str, object]) -> dict[str, object]:
    headers = request["headers"]
    assert isinstance(headers, Mapping)
    result = {**request, "headers": {k: v for k, v in headers.items() if k not in _VOLATILE_HEADERS}}
    body = request.get("body")
    if isinstance(body, Mapping) and "contents" in body:
        # The Gemini API reads a field in snake_case or camelCase alike, so only the value is compared.
        gemini = _camel_keys(body)
        assert isinstance(gemini, dict)
        result["body"] = {**gemini, "contents": _canonical_contents(gemini["contents"])}
    return result


def _requests(case: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = case["requests"]
    assert isinstance(raw, list)
    return list(raw)


def visible_requests(case: Mapping[str, object]) -> list[Mapping[str, object]]:
    """The case's requests minus the hidden fetches of the previous client library (tokenizers, config downloads)."""
    return [r for r in _requests(case) if not any(hidden in str(r["url"]) for hidden in HIDDEN_FETCHES)]


def diff_case(baseline: Mapping[str, object], current: Mapping[str, object]) -> list[Diff]:
    old = visible_requests(baseline)
    new = _requests(current)
    diffs: list[Diff] = []
    if len(old) != len(new):
        diffs.append(Diff("count", "", len(old), len(new)))
    for a, b in zip(old, new, strict=False):
        diffs.extend(_walk(_comparable(a), _comparable(b)))
    return diffs


def diff_service_case(baseline: Mapping[str, object], current: Mapping[str, object]) -> list[Diff]:
    """``diff_case`` plus the decoded result and the failure kind, for the embedding, rerank, image and search paths."""
    diffs = diff_case(baseline, current)
    diffs.extend(_walk({"result": baseline["result"]}, {"result": current["result"]}))
    if baseline["error"] != current["error"]:
        diffs.append(Diff("~", "/error", baseline["error"], current["error"]))
    return diffs


def _matches(rule: AllowedDiff, provider: str, scenario: str, diff: Diff) -> bool:
    return (
        (rule.providers is None or provider in rule.providers)
        and (rule.scenarios is None or scenario in rule.scenarios)
        and diff.kind == rule.kind
        and re.fullmatch(rule.path, diff.path) is not None
        and (rule.when is None or rule.when(diff))
    )


def explain(
    case: str, diffs: list[Diff], rules: tuple[AllowedDiff, ...] = CHAT_RULES
) -> tuple[dict[str, int], list[Diff]]:
    """({rule id: matched count}, differences no rule explains) for the case ``provider|base|scenario``."""
    provider, _, scenario = case.split("|")
    used: dict[str, int] = {}
    unexplained: list[Diff] = []
    for diff in diffs:
        rule = next((r for r in rules if _matches(r, provider, scenario, diff)), None)
        if rule is None:
            unexplained.append(diff)
        else:
            used[rule.id] = used.get(rule.id, 0) + 1
    return used, unexplained
