from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from myrm_agent_harness.agent.skill_agent.skill_reference import parse_use_tag

from app.services.agent.context_guard_service import ContextGuardService
from app.services.agent.params.workspace_resolve import (
    default_chat_workspace_path,
    resolve_default_chat_workspace_dir,
)
from app.services.chat.chat_service import ChatService


def _new_chat_id() -> str:
    return f"guard-{uuid4().hex[:12]}"


@pytest.mark.asyncio
async def test_context_guard_service_under_threshold() -> None:
    short_prompt = "Hello AI, write a quick summary of Python."
    result = await ContextGuardService.guard_inbound_prompt(
        chat_id="test_chat_short",
        raw_prompt=short_prompt,
    )
    assert not result.spilled
    assert result.sanitized_content == short_prompt
    assert result.original_char_count == len(short_prompt)


@pytest.mark.asyncio
async def test_context_guard_service_spillover_overflow() -> None:
    # Create a large prompt exceeding 16,000 characters
    large_prompt = "Critical system logs:\n" + ("ERROR 500: Database connection timed out.\n" * 400)
    assert len(large_prompt) > 16_000

    result = await ContextGuardService.guard_inbound_prompt(
        chat_id=_new_chat_id(),
        raw_prompt=large_prompt,
    )

    assert result.spilled is True
    assert result.payload is not None
    assert result.original_char_count == len(large_prompt)
    assert "<file_spillover" in result.sanitized_content
    assert "payload" in result.sanitized_content
    assert Path(result.payload.file_path).read_text(encoding="utf-8") == large_prompt


@pytest.mark.asyncio
async def test_new_chat_prompt_spills_into_the_workspace_the_agent_runs_in() -> None:
    """A new chat has no row until its first assistant output, yet the model must find the file."""
    chat_id = _new_chat_id()
    prompt = "needle-line\n" * 2_000

    result = await ContextGuardService.guard_inbound_prompt(chat_id=chat_id, raw_prompt=prompt)

    assert result.payload is not None
    agent_workspace = await resolve_default_chat_workspace_dir(chat_id, persist_workspace=False)
    assert agent_workspace is not None
    assert (Path(agent_workspace) / result.payload.relative_path).read_text(encoding="utf-8") == prompt


@pytest.mark.asyncio
async def test_existing_chat_prompt_spills_into_its_bound_workspace(tmp_path: Path) -> None:
    chat_id = _new_chat_id()
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=chat_id,
        content="hello",
        sent_at=datetime.now(tz=UTC),
        sent_timezone="UTC",
        message_id=str(uuid4()),
    )
    await ChatService.update_chat_fields(chat_id, {"workspace_dir": str(tmp_path)})
    prompt = "bound-line\n" * 2_000

    result = await ContextGuardService.guard_inbound_prompt(chat_id=chat_id, raw_prompt=prompt)

    assert result.payload is not None
    assert (tmp_path / result.payload.relative_path).read_text(encoding="utf-8") == prompt


@pytest.mark.asyncio
async def test_spilled_prompt_keeps_an_explicit_skill_invocation_in_front() -> None:
    """The harness only recognizes ``[use skill]`` at the very start of the user's text."""
    prompt = "[use pdf-skill] summarize this report\n" + "report-line\n" * 2_000

    result = await ContextGuardService.guard_inbound_prompt(chat_id=_new_chat_id(), raw_prompt=prompt)

    assert result.spilled is True
    invocation = parse_use_tag(result.sanitized_content)
    assert invocation is not None
    assert invocation.references == ("pdf-skill",)
    assert invocation.text.startswith("<file_spillover path=")


@pytest.mark.asyncio
async def test_spilled_prompt_without_an_invocation_starts_with_the_reference() -> None:
    prompt = "see [use pdf-skill] later\n" + "report-line\n" * 2_000

    result = await ContextGuardService.guard_inbound_prompt(chat_id=_new_chat_id(), raw_prompt=prompt)

    assert result.spilled is True
    assert result.sanitized_content.startswith("<file_spillover path=")


@pytest.mark.asyncio
async def test_prompt_without_a_chat_stays_intact() -> None:
    """With no workspace the agent could read, replacing the prompt by a file reference loses it."""
    prompt = "orphan-line\n" * 2_000

    result = await ContextGuardService.guard_inbound_prompt(chat_id=None, raw_prompt=prompt)

    assert result.spilled is False
    assert result.sanitized_content == prompt
    assert result.original_char_count == len(prompt)


@pytest.mark.parametrize("unsafe_chat_id", ["../escape", "a/b", "a\\b", "x..y", "x:y", "x y"])
def test_default_chat_workspace_path_rejects_ids_that_cannot_name_a_workspace(unsafe_chat_id: str) -> None:
    with pytest.raises(ValueError, match="Invalid chat workspace id"):
        default_chat_workspace_path(unsafe_chat_id)


@pytest.mark.asyncio
async def test_prompt_of_a_chat_whose_id_cannot_name_a_workspace_stays_intact() -> None:
    """The id is untrusted input: it must never steer the spill file out of the workspaces root."""
    prompt = "escape-line\n" * 2_000

    result = await ContextGuardService.guard_inbound_prompt(chat_id="../escape", raw_prompt=prompt)

    assert result.spilled is False
    assert result.sanitized_content == prompt


@pytest.mark.asyncio
async def test_small_prompt_of_a_new_chat_creates_no_workspace() -> None:
    """The lazy session gate keeps empty sessions from leaving directories behind."""
    chat_id = _new_chat_id()

    await ContextGuardService.guard_inbound_prompt(chat_id=chat_id, raw_prompt="hello")

    assert not default_chat_workspace_path(chat_id).exists()


@pytest.mark.asyncio
async def test_default_chat_workspace_path_is_where_the_agent_workspace_gets_created() -> None:
    chat_id = _new_chat_id()
    expected = default_chat_workspace_path(chat_id)
    assert not expected.exists()

    created = await resolve_default_chat_workspace_dir(chat_id, persist_workspace=False)

    assert created is not None
    assert Path(created) == expected


def test_default_sweep_covers_the_chat_workspaces() -> None:
    spill_dir = default_chat_workspace_path(_new_chat_id()) / ".myrm" / "spillover"
    spill_dir.mkdir(parents=True)
    expired_file = spill_dir / "payload_old.md"
    expired_file.write_text("old logs", encoding="utf-8")
    os.utime(expired_file, (1000.0, 1000.0))

    cleaned = ContextGuardService.sweep_all_workspaces()

    assert cleaned >= 1
    assert not expired_file.exists()


def test_context_guard_service_sweep_workspaces() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root_path = Path(tmpdir)
        chat_dir = root_path / "chat_123"
        spillover_dir = chat_dir / ".myrm/spillover"
        spillover_dir.mkdir(parents=True, exist_ok=True)

        expired_file = spillover_dir / "payload_old.md"
        expired_file.write_text("old logs", encoding="utf-8")

        # Mock mtime 2 days ago
        past_time = 1000.0
        os.utime(expired_file, (past_time, past_time))

        cleaned = ContextGuardService.sweep_all_workspaces(root_dir=root_path)
        assert cleaned == 1
        assert not expired_file.exists()
