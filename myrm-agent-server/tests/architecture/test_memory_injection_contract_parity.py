"""Architecture test: frontend memory injection union stays in sync with harness contract."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from myrm_agent_harness.api.hooks import get_memory_runtime_injection_contract

from app.services.agent.stream_session._memory_status_helpers import (
    get_memory_brief_status_contract,
)

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_MYRM_AGENT_ROOT = _SERVER_ROOT.parent
_FRONTEND_TYPES = (
    _MYRM_AGENT_ROOT
    / "myrm-agent-frontend"
    / "src"
    / "store"
    / "chat"
    / "types"
    / "agentStream"
    / "part2.ts"
)


def _extract_interface_block(content: str, interface_name: str) -> str:
    match = re.search(
        rf"export interface {re.escape(interface_name)}\s*\{{(.*?)\n\}}",
        content,
        re.DOTALL,
    )
    assert match is not None, f"{interface_name} block not found in part2.ts"
    return match.group(1)


def _extract_union_literals(block: str, field_name: str) -> frozenset[str]:
    match = re.search(rf"{re.escape(field_name)}\??:\s*(.+?);", block, re.DOTALL)
    assert match is not None, f"{field_name} union not found in MemoryBriefInjectionStatus"
    return frozenset(re.findall(r"'([^']+)'", match.group(1)))


@pytest.mark.architecture
def test_frontend_memory_injection_union_matches_harness_contract() -> None:
    ts_content = _FRONTEND_TYPES.read_text(encoding="utf-8")
    injection_block = _extract_interface_block(ts_content, "MemoryBriefInjectionStatus")
    ts_states = _extract_union_literals(injection_block, "state")
    ts_sources = _extract_union_literals(injection_block, "source")
    ts_reasons = _extract_union_literals(injection_block, "reason")

    contract = get_memory_runtime_injection_contract()
    py_states = frozenset(contract["states"])
    py_sources = frozenset(contract["sources"])
    py_reasons = frozenset(contract["reasons"])

    assert ts_states == py_states, f"state union mismatch: ts={sorted(ts_states)} py={sorted(py_states)}"
    assert ts_sources == py_sources, f"source union mismatch: ts={sorted(ts_sources)} py={sorted(py_sources)}"
    assert ts_reasons == py_reasons, f"reason union mismatch: ts={sorted(ts_reasons)} py={sorted(py_reasons)}"


@pytest.mark.architecture
def test_frontend_memory_brief_status_union_matches_server_contract() -> None:
    ts_content = _FRONTEND_TYPES.read_text(encoding="utf-8")
    brief_block = _extract_interface_block(ts_content, "MemoryBriefStatus")
    ts_states = _extract_union_literals(brief_block, "state")
    ts_reasons = _extract_union_literals(brief_block, "reason")
    ts_sources = _extract_union_literals(brief_block, "source")

    contract = get_memory_brief_status_contract()
    py_states = frozenset(contract["states"])
    py_reasons = frozenset(contract["reasons"])
    py_sources = frozenset(contract["sources"])

    assert ts_states == py_states, f"brief state mismatch: ts={sorted(ts_states)} py={sorted(py_states)}"
    assert ts_reasons == py_reasons, f"brief reason mismatch: ts={sorted(ts_reasons)} py={sorted(py_reasons)}"
    assert ts_sources == py_sources, f"brief source mismatch: ts={sorted(ts_sources)} py={sorted(py_sources)}"
