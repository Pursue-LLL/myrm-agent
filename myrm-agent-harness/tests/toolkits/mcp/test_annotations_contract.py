"""Contract of a server's declared tool annotations, from the wire to the scheduler, over both transports.

A real MCP server declares hints on its tools; the production connection pool converts, processes and registers them.
These tests read what the pool produced: the declarations ride in the tool's own metadata field and nowhere else, the
registry holds the judged record, and the one thing a clean read-only claim opens (running beside other tools) really
happens through the conflict gate, while a destructive, contradictory or undeclared tool still runs alone.

[INPUT]
- tests.support.mcp_testkit.probe_connection::connect_probe_server, ProbeServer (POS: the probe server seen through the production pool)
- tests.support.mcp_testkit.annotations_probe_server::DECLARED (POS: what each probe tool declares)
- myrm_agent_harness.agent.middlewares.concurrency.tool_conflict_gate::ToolConflictGateMiddleware (POS: the one reader of the parallel-safety bit)

[OUTPUT]
- Tests of the hand-off of declarations, the judged registry record, the claim slot, host serialization and scheduling.

[POS]
End-to-end guard for the repaired hand-off: a regression that drops the declarations, writes them where a consumer
reads them as facts, or lets a claim reach the people and models that approve, fails here.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from langchain.agents.middleware import ToolCallRequest
from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.middlewares.concurrency.tool_conflict_gate import ToolConflictGateMiddleware
from myrm_agent_harness.core.security.tool_registry import MCPAnnotations, SafetyMetadata, resolve_safety_metadata
from myrm_agent_harness.toolkits.mcp.annotations import recorded_annotations
from tests.support.mcp_testkit.annotations_probe_server import DECLARED
from tests.support.mcp_testkit.probe_connection import ProbeServer, connect_probe_server

# Declares itself read-only and not destructive: the only tools that may run beside others.
_RUN_BESIDE_OTHERS = {"read_only", "liar_write", "fetch_web", "append_item", "list_items"}
_DESTRUCTIVE = {"delete_it", "contradict"}
_CLAIMS: dict[str, MCPAnnotations] = {
    "delete_it": {"destructiveHint": True},
    "contradict": {"destructiveHint": True},
    "fetch_web": {"openWorldHint": True},
}
_FLAT_HINTS = {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}
_BUILTIN_READ = "file_read_tool"


@dataclass(frozen=True, slots=True)
class Seen:
    """The probe server and what the pool registered for it while connecting."""

    probe: ProbeServer
    records: dict[str, tuple[SafetyMetadata, MCPAnnotations]]


@pytest_asyncio.fixture(scope="module", params=("stdio", "streamable_http"))
async def seen(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[Seen]:
    async with connect_probe_server(request.param, tmp_path_factory.mktemp("probe")) as probe:
        yield Seen(probe, probe.registered())


def test_declarations_ride_in_their_own_metadata_field(seen: Seen) -> None:
    for name, tool in seen.probe.tools.items():
        assert recorded_annotations(tool) == DECLARED.get(name, {}), name
        assert not _FLAT_HINTS & set(tool.metadata or {}), f"{name}: a hint must never be a flat metadata key"


def test_every_tool_is_registered_with_the_judged_record(seen: Seen) -> None:
    assert set(seen.records) == set(seen.probe.tools)

    for name, (record, claims) in seen.records.items():
        assert record.is_concurrent_safe == (name in _RUN_BESIDE_OTHERS), name
        assert record.is_destructive == (name in _DESTRUCTIVE), name
        assert not record.is_read_only, f"{name}: a server's word must not make a tool read-only for the host"
        assert not record.is_idempotent, name
        assert claims == _CLAIMS.get(name, {}), name


def test_a_claim_that_reassures_is_never_kept(seen: Seen) -> None:
    for name, (_record, claims) in seen.records.items():
        assert set(claims) <= {"destructiveHint", "openWorldHint"}, name
        assert all(value is True for value in claims.values()), name


def test_the_scheduler_reads_the_same_record(seen: Seen) -> None:
    seen.probe.register()

    for name, tool in seen.probe.tools.items():
        record, _claims = seen.records[name]
        assert resolve_safety_metadata(tool.name) == record, name


def _request(name: str, call_id: str) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "id": call_id, "args": {}, "type": "tool_call"},
        tool=None,
        state={"messages": []},
        runtime=MagicMock(),
    )


async def _runs_beside(first: str, second: str) -> bool:
    """Whether the conflict gate lets the second call start while the first is still running."""
    started: list[str] = []
    release = asyncio.Event()

    async def handle(request: ToolCallRequest) -> ToolMessage:
        call_id = request.tool_call["id"] or ""
        started.append(call_id)
        await release.wait()
        return ToolMessage(content="ok", tool_call_id=call_id)

    gate = ToolConflictGateMiddleware()
    calls = [
        asyncio.create_task(gate.awrap_tool_call(_request(name, f"call-{index}"), handle))
        for index, name in enumerate((first, second))
    ]
    for _ in range(8):
        await asyncio.sleep(0)
    beside = len(started) == 2
    release.set()
    await asyncio.wait_for(asyncio.gather(*calls), timeout=5)
    return beside


async def test_only_a_clean_read_only_claim_runs_beside_another_tool(seen: Seen) -> None:
    seen.probe.register()

    for name in seen.probe.tools:
        beside = await _runs_beside(seen.probe.call_name(name), _BUILTIN_READ)

        assert beside == (name in _RUN_BESIDE_OTHERS), name


async def test_a_host_serial_server_never_runs_beside_another_tool(tmp_path_factory: pytest.TempPathFactory) -> None:
    async with connect_probe_server("streamable_http", tmp_path_factory.mktemp("serial"), host_serial=True) as probe:
        records = probe.registered()
        assert not any(record.is_concurrent_safe for record, _claims in records.values())
        assert records["delete_it"][1] == {"destructiveHint": True}

        assert not await _runs_beside(probe.call_name("read_only"), _BUILTIN_READ)
