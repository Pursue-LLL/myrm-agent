"""LiteLLM routing: the generated frontend prefixes must equal the harness routing table.

[POS]
tests/architecture/test_litellm_routing_frontend_parity.py

[INPUT]
- myrm_agent_harness agent.config.litellm_routing: `BUILTIN_PROVIDER_LITELLM_SEGMENT`, `known_litellm_route_segments_ordered`
- myrm-agent-frontend litellmRouting.generated.ts: `KNOWN_LITELLM_ROUTE_PREFIXES`, `PROVIDER_TO_LITELLM_PREFIX`

[OUTPUT]
- Fails when the generated file lists other prefixes (or the same ones in another order) or maps a provider to a
  different prefix than the harness table: the settings UI would then build model ids LiteLLM does not route
"""

from __future__ import annotations

import re

import pytest
from myrm_agent_harness.agent.config.litellm_routing import (
    BUILTIN_PROVIDER_LITELLM_SEGMENT,
    known_litellm_route_segments_ordered,
)

from tests.support.frontend_api_paths import FRONTEND_SRC

pytestmark = pytest.mark.architecture

_GENERATED = FRONTEND_SRC / "store" / "config" / "litellmRouting.generated.ts"

# Values only: the generator's quoting and key quoting are not part of the contract.
_PREFIXES_RE = re.compile(r"KNOWN_LITELLM_ROUTE_PREFIXES\b[^=]*=\s*\[(?P<body>.*?)\]", re.DOTALL)
_MAP_RE = re.compile(r"PROVIDER_TO_LITELLM_PREFIX\b[^=]*=\s*\{(?P<body>.*?)\}", re.DOTALL)
_QUOTED_RE = re.compile(r"""['"]([\w-]+)['"]""")
_ENTRY_RE = re.compile(r"""['"]?([\w-]+)['"]?\s*:\s*['"]([\w-]+)['"]""")


def _parse_prefixes(source: str) -> list[str]:
    match = _PREFIXES_RE.search(source)
    assert match, "KNOWN_LITELLM_ROUTE_PREFIXES list not found in the generated routing file"
    prefixes = _QUOTED_RE.findall(match.group("body"))
    assert prefixes, "KNOWN_LITELLM_ROUTE_PREFIXES has no entries"
    return prefixes


def _parse_provider_map(source: str) -> dict[str, str]:
    match = _MAP_RE.search(source)
    assert match, "PROVIDER_TO_LITELLM_PREFIX map not found in the generated routing file"
    entries = dict(_ENTRY_RE.findall(match.group("body")))
    assert entries, "PROVIDER_TO_LITELLM_PREFIX has no entries"
    return entries


def _drift(source: str) -> list[str]:
    """Differences between the generated file's text and the harness routing table."""
    problems: list[str] = []

    expected_prefixes = list(known_litellm_route_segments_ordered())
    prefixes = _parse_prefixes(source)
    if prefixes != expected_prefixes:
        problems.append(f"KNOWN_LITELLM_ROUTE_PREFIXES is {prefixes}, the harness table gives {expected_prefixes}")

    mapping = _parse_provider_map(source)
    missing = sorted(BUILTIN_PROVIDER_LITELLM_SEGMENT.keys() - mapping.keys())
    extra = sorted(mapping.keys() - BUILTIN_PROVIDER_LITELLM_SEGMENT.keys())
    changed = {
        provider: (mapping[provider], segment)
        for provider, segment in BUILTIN_PROVIDER_LITELLM_SEGMENT.items()
        if provider in mapping and mapping[provider] != segment
    }
    if missing:
        problems.append(f"PROVIDER_TO_LITELLM_PREFIX lacks providers the harness routes: {missing}")
    if extra:
        problems.append(f"PROVIDER_TO_LITELLM_PREFIX lists providers the harness does not route: {extra}")
    if changed:
        problems.append(f"PROVIDER_TO_LITELLM_PREFIX maps to other prefixes (generated, harness): {changed}")
    return problems


def _render(prefixes: list[str], mapping: dict[str, str]) -> str:
    """The generated file's shape, in the double-quoted style a code generator writes."""
    listed = "".join(f'  "{prefix}",\n' for prefix in prefixes)
    mapped = "".join(f'  "{provider}": "{segment}",\n' for provider, segment in sorted(mapping.items()))
    return (
        f"export const KNOWN_LITELLM_ROUTE_PREFIXES: readonly string[] = [\n{listed}] as const;\n\n"
        f"export const PROVIDER_TO_LITELLM_PREFIX: Record<string, string> = {{\n{mapped}}};\n"
    )


@pytest.mark.skipif(not _GENERATED.is_file(), reason="frontend sources are not part of this checkout")
def test_generated_frontend_routing_matches_the_harness_table() -> None:
    problems = _drift(_GENERATED.read_text(encoding="utf-8"))

    assert not problems, (
        "litellmRouting.generated.ts has drifted from the harness routing table (regenerate it from "
        "myrm_agent_harness.agent.config.litellm_routing; resolveLiteLLMRoutePrefix falls back to the provider id "
        "for a provider the map lacks, and requests then fail):\n" + "\n".join(problems)
    )


def test_drift_check_reads_both_generator_and_hand_written_quoting() -> None:
    prefixes = list(known_litellm_route_segments_ordered())
    mapping = dict(BUILTIN_PROVIDER_LITELLM_SEGMENT)

    assert _drift(_render(prefixes, mapping)) == []
    assert _drift(_render(prefixes, mapping).replace('"', "'")) == []


_SEGMENTS = list(known_litellm_route_segments_ordered())
_TABLE = dict(BUILTIN_PROVIDER_LITELLM_SEGMENT)


@pytest.mark.parametrize(
    ("label", "prefixes", "mapping"),
    [
        ("prefix missing", _SEGMENTS[1:], _TABLE),
        ("prefixes reordered", _SEGMENTS[::-1], _TABLE),
        ("provider missing", _SEGMENTS, dict(list(_TABLE.items())[1:])),
        ("provider added", _SEGMENTS, {**_TABLE, "not_a_provider": "openai"}),
        ("provider mapped elsewhere", _SEGMENTS, {**_TABLE, "openai": "azure"}),
    ],
)
def test_drift_check_reports_every_kind_of_drift(label: str, prefixes: list[str], mapping: dict[str, str]) -> None:
    assert _drift(_render(prefixes, mapping)), label
