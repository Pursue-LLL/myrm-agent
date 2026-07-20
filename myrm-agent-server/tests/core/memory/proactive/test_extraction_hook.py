"""Tests for commitment extraction hook and ISO parsing."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.memory.proactive import CommitmentExtractor
from myrm_agent_harness.toolkits.memory.proactive.types import (
    CommitmentCandidate,
    CommitmentKind,
    CommitmentSensitivity,
)


@pytest.mark.asyncio
async def test_parse_iso_to_ms_valid_and_invalid() -> None:
    from app.core.memory.proactive.extraction_hook import _parse_iso_to_ms

    assert _parse_iso_to_ms("2026-06-01T12:00:00Z") is not None
    assert _parse_iso_to_ms("not-a-date") is None


@pytest.mark.asyncio
async def test_run_commitment_extraction_no_candidates() -> None:
    from app.core.memory.proactive.extraction_hook import run_commitment_extraction

    llm_func = AsyncMock(return_value="{}")
    with patch.object(CommitmentExtractor, "extract", AsyncMock(return_value=[])):
        created = await run_commitment_extraction(
            [{"role": "user", "content": "hello"}],
            llm_func,
            agent_id="hook-empty-agent",
            user_id="default",
        )
    assert created == 0


@pytest.mark.asyncio
async def test_run_commitment_extraction_persists_candidate() -> None:
    from app.core.memory.proactive.extraction_hook import run_commitment_extraction

    now_iso = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    candidate = CommitmentCandidate(
        kind=CommitmentKind.EVENT_CHECK_IN,
        sensitivity=CommitmentSensitivity.ROUTINE,
        reason="interview Friday",
        suggested_text="How is interview prep?",
        dedupe_key="interview-friday",
        confidence=0.9,
        due_window_earliest=now_iso,
        due_window_latest=None,
        due_window_timezone="UTC",
    )
    llm_func = AsyncMock(return_value="{}")

    with patch.object(CommitmentExtractor, "extract", AsyncMock(return_value=[candidate])):
        created = await run_commitment_extraction(
            [{"role": "user", "content": "Interview on Friday"}],
            llm_func,
            agent_id="hook-persist-agent",
            user_id="default",
            source_chat_id="chat-1",
        )

    assert created == 1

    from app.core.memory.proactive.sqlite_store import SqlAlchemyCommitmentStore

    store = SqlAlchemyCommitmentStore()
    items = await store.list_all(user_id="default", agent_id="hook-persist-agent")
    assert len(items) == 1
    assert items[0].source_chat_id == "chat-1"
    assert items[0].dedupe_key == "interview-friday"


@pytest.mark.asyncio
async def test_run_commitment_extraction_skips_invalid_due_window() -> None:
    from app.core.memory.proactive.extraction_hook import run_commitment_extraction

    candidate = CommitmentCandidate(
        kind=CommitmentKind.OPEN_LOOP,
        sensitivity=CommitmentSensitivity.ROUTINE,
        reason="bad date",
        suggested_text="check",
        dedupe_key="bad-date",
        confidence=0.7,
        due_window_earliest="invalid",
    )
    llm_func = AsyncMock(return_value="{}")

    with patch.object(CommitmentExtractor, "extract", AsyncMock(return_value=[candidate])):
        created = await run_commitment_extraction(
            [{"role": "user", "content": "waiting"}],
            llm_func,
            agent_id="hook-invalid-agent",
            user_id="default",
        )

    assert created == 0
