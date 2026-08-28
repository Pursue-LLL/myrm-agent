"""Integration tests for pattern discovery API wiring (real router + real DB).

Covers the full request chain for ``POST /trigger-pattern-discovery`` and
``GET /pattern-discoveries``:

- POST follows the real router -> memory_guardian delegate ->
  ``pattern_discovery_trigger.run_pattern_discovery_once`` chain.
- WebUI default model is not configured in the test DB, so the real
  ``load_platform_llm`` fast-path ends in a graceful skip —
  this is the exact behavior that revived the previously dead feature path.
- With an injected harness result, the real ledger write is persisted and
  read back through ``GET /pattern-discoveries`` with a user-readable,
  non-technical summary (no ``duration_ms`` leakage).

Only the harness boundary is stubbed (LLM build + strategy result); the
router, delegate, config loading, ledger persistence and readback are real.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api.memory.operations import guardian as guardian_operation
from app.database.models.memory import MemoryOperationEventModel
from app.lifecycle import pattern_discovery_trigger

pytestmark = pytest.mark.integration


class _Pattern(BaseModel):
    """Pydantic stand-in matching the harness Pattern model surface."""

    title: str
    confidence: float
    description: str
    evidence: list[str]
    tags: list[str]


@pytest.fixture(autouse=True)
def _clean_operation_ledger() -> Iterator[None]:
    """Truncate the operation ledger before each test for DB isolation."""
    from app.database.connection import get_session

    async def _truncate() -> None:
        async with get_session() as db:
            await db.execute(MemoryOperationEventModel.__table__.delete())
            await db.commit()

    asyncio.run(_truncate())
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Real-DB API client mounting only the guardian router.

    ``get_db_session`` is intentionally NOT overridden so ``GET
    /pattern-discoveries`` reads the real (empty, schema-initialized by the
    session-level autouse fixture) operation_ledger table.
    """
    app = FastAPI()
    app.include_router(guardian_operation.router, prefix="/api/v1/memory")
    with TestClient(app) as test_client:
        yield test_client


def _report(pattern_count: int = 1, skipped: bool = False, skip_reason: str | None = None) -> SimpleNamespace:
    """Build a harness PatternReport stand-in (harness boundary stub)."""
    patterns = [
        _Pattern(
            title=f"pattern-{i}",
            confidence=0.9,
            description="user keeps working in short focused sessions",
            evidence=["mem-1"],
            tags=["focus"],
        )
        for i in range(pattern_count)
    ]
    return SimpleNamespace(
        patterns=patterns,
        has_patterns=pattern_count > 0,
        memory_count=60,
        insight_count=12,
        duration_ms=1234.5,
        meta_observation="user consistently applies a short-focus workflow",
        skipped=skipped,
        skip_reason=skip_reason,
    )


def _stub_llm() -> MagicMock:
    return MagicMock()


def test_trigger_pattern_discovery_skips_gracefully_without_platform_model(client: TestClient) -> None:
    """POST follows the real chain; no platform model -> graceful skipped result.

    Critical path is unmocked: the route, delegate, LLM construction from
    ``load_platform_llm`` and the empty config DB read are all real.
    """
    response = client.post("/api/v1/memory/guardian/trigger-pattern-discovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["triggered"] is True
    assert payload["skipped"] is True
    assert "reason" in payload


def test_pattern_discoveries_returns_empty_on_fresh_db(client: TestClient) -> None:
    """GET reads the real operation_ledger table (empty in the isolated test DB)."""
    response = client.get("/api/v1/memory/guardian/pattern-discoveries")

    assert response.status_code == 200
    assert response.json() == []


def test_trigger_with_result_records_user_readable_summary_read_back(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Injected harness result flows through a real ledger write and read-back.

    The summary is persisted and returned without technical detail leakage
    (``duration_ms`` stays in ``metadata`` only).
    """
    llm = _stub_llm()
    report = _report(pattern_count=2)
    monkeypatch.setattr(pattern_discovery_trigger, "_build_platform_llm", AsyncMock(return_value=llm))
    manager = MagicMock()
    monkeypatch.setattr(
        "app.lifecycle.memory_guardian_ops.create_guardian_memory_manager",
        AsyncMock(return_value=manager),
    )
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.memory.strategies.pattern_discovery.run_pattern_discovery",
        AsyncMock(return_value=report),
    )

    post_response = client.post("/api/v1/memory/guardian/trigger-pattern-discovery")

    assert post_response.status_code == 200
    post_payload = post_response.json()
    assert post_payload["triggered"] is True
    assert post_payload["skipped"] is False
    assert post_payload["pattern_count"] == 2

    get_response = client.get("/api/v1/memory/guardian/pattern-discoveries")
    assert get_response.status_code == 200
    events = get_response.json()
    assert len(events) == 1
    event = events[0]
    assert event["summary"] == "Pattern discovery: identified 2 new behavioral pattern(s)."
    assert "duration_ms" not in event["summary"]
    metadata = event["metadata"]
    assert metadata["operation"] == "pattern_discovery"
    assert metadata["pattern_count"] == 2
    assert "duration_ms" in metadata
    assert len(metadata["patterns"]) == 2


def test_trigger_skipped_report_does_not_persist_event(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A harness-level skipped report (maturity gate) records nothing to the ledger."""
    llm = _stub_llm()
    monkeypatch.setattr(pattern_discovery_trigger, "_build_platform_llm", AsyncMock(return_value=llm))
    manager = MagicMock()
    monkeypatch.setattr(
        "app.lifecycle.memory_guardian_ops.create_guardian_memory_manager",
        AsyncMock(return_value=manager),
    )
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.memory.strategies.pattern_discovery.run_pattern_discovery",
        AsyncMock(return_value=_report(pattern_count=0, skipped=True, skip_reason="memory count below maturity gate (50)")),
    )

    response = client.post("/api/v1/memory/guardian/trigger-pattern-discovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["triggered"] is True
    assert payload["skipped"] is True
    assert "memory count below maturity gate" in payload["reason"]

    assert client.get("/api/v1/memory/guardian/pattern-discoveries").json() == []
