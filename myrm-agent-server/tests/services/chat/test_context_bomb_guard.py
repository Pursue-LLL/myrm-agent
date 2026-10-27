from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest
from myrm_agent_harness.agent.context_guard import KEPT_SPILLOVER_DIR, TRANSIENT_SPILLOVER_DIR
from myrm_agent_harness.agent.skill_agent.skill_reference import parse_use_tag

from app.services.chat.context_bomb_guard import (
    USER_TEXT_LIMITS,
    ContextBombDefenseService,
    SpilloverPayloadResult,
    extract_text_from_query,
    replace_query_text,
)
from tests.support.oversized_paste import paste_between_the_limits, paste_over_the_limit

_OVERSIZED = paste_over_the_limit()


def test_extract_text_from_query() -> None:
    assert extract_text_from_query("simple string") == "simple string"
    assert extract_text_from_query([{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]) == "hello\nworld"
    assert extract_text_from_query([{"content": "direct content"}]) == "direct content"
    assert extract_text_from_query(12345) == ""


def test_replace_query_text_keeps_the_other_blocks() -> None:
    image_block: dict[str, object] = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}

    replaced = replace_query_text([{"type": "text", "text": "a"}, image_block, {"type": "text", "text": "b"}], "stub")

    assert replaced == [{"type": "text", "text": "stub"}, image_block]


def test_process_incoming_content_under_threshold(tmp_path: Path) -> None:
    text = "Short user prompt."

    res = ContextBombDefenseService.process_incoming_content(text, workspace_root=tmp_path)

    assert res == SpilloverPayloadResult.intact(text)
    assert res.original_char_count == len(text)
    assert not (tmp_path / ".myrm").exists()


def test_process_incoming_content_over_threshold(tmp_path: Path) -> None:
    raw_content = _OVERSIZED + "\nDetailed instructions follow here..."

    res = ContextBombDefenseService.process_incoming_content(raw_content, workspace_root=tmp_path)

    assert res.is_spilled
    assert res.original_char_count == len(raw_content)
    assert res.spillover_path is not None
    assert res.content_sha256 == hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
    assert Path(res.spillover_path).read_text(encoding="utf-8") == raw_content
    assert res.relative_path is not None and res.relative_path.startswith(f"{TRANSIENT_SPILLOVER_DIR}/")
    assert "<file_spillover path=" in res.processed_content
    assert res.relative_path in res.processed_content
    assert str(tmp_path) not in res.processed_content
    assert "file_read_tool" in res.processed_content


def test_a_kept_text_lands_in_the_paste_directory_and_a_transient_one_does_not(tmp_path: Path) -> None:
    kept = ContextBombDefenseService.process_incoming_content(_OVERSIZED, workspace_root=tmp_path, kept=True)
    transient = ContextBombDefenseService.process_incoming_content(_OVERSIZED, workspace_root=tmp_path)

    assert kept.relative_path is not None and kept.relative_path.startswith(f"{KEPT_SPILLOVER_DIR}/")
    assert transient.relative_path is not None and transient.relative_path.startswith(f"{TRANSIENT_SPILLOVER_DIR}/")


def test_a_text_without_a_workspace_stays_as_it_is() -> None:
    result = ContextBombDefenseService.process_incoming_content(_OVERSIZED, workspace_root=None, kept=True)

    assert not result.is_spilled
    assert result.processed_content == _OVERSIZED


def test_the_same_text_parks_into_the_same_file_and_the_same_stub(tmp_path: Path) -> None:
    first = ContextBombDefenseService.process_incoming_content(_OVERSIZED, workspace_root=tmp_path, kept=True)
    second = ContextBombDefenseService.process_incoming_content(_OVERSIZED, workspace_root=tmp_path, kept=True)

    assert first.processed_content == second.processed_content
    assert first.spillover_path == second.spillover_path
    assert len(list((tmp_path / KEPT_SPILLOVER_DIR).glob("payload_*.md"))) == 1


def test_the_stub_shows_the_end_of_the_text_so_a_trailing_question_is_not_lost(tmp_path: Path) -> None:
    text = paste_over_the_limit("log-line\n") + "QUESTION: which service failed first?"

    res = ContextBombDefenseService.process_incoming_content(text, workspace_root=tmp_path, kept=True)

    assert "QUESTION: which service failed first?" in res.processed_content


def test_an_unwritable_workspace_raises_so_that_callers_keep_the_text(tmp_path: Path) -> None:
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("a file where the workspace should be", encoding="utf-8")

    with pytest.raises(OSError):
        ContextBombDefenseService.process_incoming_content(_OVERSIZED, workspace_root=blocked, kept=True)


def test_guard_and_spill_query_under_limit(tmp_path: Path) -> None:
    query = "Short user prompt"

    transformed, parked = ContextBombDefenseService.guard_and_spill_query(query, workspace_dir=tmp_path)

    assert transformed == query
    assert not parked.is_spilled


def test_guard_and_spill_query_over_limit_parks_the_text_for_good(tmp_path: Path) -> None:
    transformed, parked = ContextBombDefenseService.guard_and_spill_query(_OVERSIZED, workspace_dir=tmp_path)

    assert parked.is_spilled
    assert parked.content_sha256 is not None and len(parked.content_sha256) == 64
    assert transformed == parked.processed_content
    assert isinstance(transformed, str) and "<file_spillover path=" in transformed
    assert parked.relative_path is not None and parked.relative_path.startswith(f"{KEPT_SPILLOVER_DIR}/")
    assert (tmp_path / parked.relative_path).read_text(encoding="utf-8") == _OVERSIZED


def test_a_query_without_a_workspace_stays_whole() -> None:
    transformed, parked = ContextBombDefenseService.guard_and_spill_query(_OVERSIZED, workspace_dir=None)

    assert transformed == _OVERSIZED
    assert not parked.is_spilled


def test_a_query_whose_file_cannot_be_written_stays_whole(tmp_path: Path) -> None:
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("a file where the workspace should be", encoding="utf-8")

    transformed, parked = ContextBombDefenseService.guard_and_spill_query(_OVERSIZED, workspace_dir=blocked)

    assert transformed == _OVERSIZED
    assert not parked.is_spilled


def test_the_stub_of_a_query_and_of_a_stored_message_are_the_same_bytes(tmp_path: Path) -> None:
    """The live turn and the history rebuilt from the database must carry one and the same reference."""
    _, as_query = ContextBombDefenseService.guard_and_spill_query(_OVERSIZED, workspace_dir=tmp_path)
    as_message = ContextBombDefenseService.process_incoming_content(_OVERSIZED, workspace_root=tmp_path, kept=True)

    assert as_query.processed_content == as_message.processed_content


def test_spilled_query_keeps_an_explicit_skill_invocation_in_front(tmp_path: Path) -> None:
    """The harness only recognizes ``[use skill]`` at the very start of the user's text."""
    query = "[use pdf-skill] " + _OVERSIZED

    transformed, parked = ContextBombDefenseService.guard_and_spill_query(query, workspace_dir=tmp_path)

    assert parked.is_spilled
    assert isinstance(transformed, str)
    invocation = parse_use_tag(transformed)
    assert invocation is not None
    assert invocation.references == ("pdf-skill",)
    assert invocation.text.startswith("<file_spillover path=")


def test_spilled_attachment_query_keeps_an_explicit_skill_invocation_in_its_first_text_block(tmp_path: Path) -> None:
    image_block: dict[str, object] = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    query: list[dict[str, object]] = [{"type": "text", "text": "[use pdf-skill] " + _OVERSIZED}, image_block]

    transformed, parked = ContextBombDefenseService.guard_and_spill_query(query, workspace_dir=tmp_path)

    assert parked.is_spilled
    assert isinstance(transformed, list)
    assert transformed[1:] == [image_block]
    first_text = transformed[0]["text"]
    assert isinstance(first_text, str)
    invocation = parse_use_tag(first_text)
    assert invocation is not None
    assert invocation.references == ("pdf-skill",)
    assert invocation.text.startswith("<file_spillover path=")


def test_spilled_message_keeps_an_explicit_skill_invocation_in_front(tmp_path: Path) -> None:
    """Persisted user messages go through the same spill: the turn's invocation must stay readable in history."""
    res = ContextBombDefenseService.process_incoming_content("[use pdf-skill] " + _OVERSIZED, workspace_root=tmp_path, kept=True)

    assert res.is_spilled
    invocation = parse_use_tag(res.processed_content)
    assert invocation is not None
    assert invocation.references == ("pdf-skill",)
    assert invocation.text.startswith("<file_spillover path=")


def test_a_text_within_the_limit_of_a_person_goes_into_the_prompt_as_it_is(tmp_path: Path) -> None:
    text = paste_between_the_limits()

    res = ContextBombDefenseService.process_incoming_content(text, workspace_root=tmp_path, kept=True)

    assert not ContextBombDefenseService.is_oversized(text)
    assert res == SpilloverPayloadResult.intact(text)
    assert not (tmp_path / ".myrm").exists()


def test_a_document_of_that_size_is_parked_all_the_same_for_it_is_third_party_text(tmp_path: Path) -> None:
    res = ContextBombDefenseService.process_incoming_content(paste_between_the_limits(), workspace_root=tmp_path)

    assert res.is_spilled
    assert res.relative_path is not None and res.relative_path.startswith(f"{TRANSIENT_SPILLOVER_DIR}/")


@pytest.mark.parametrize(
    ("text", "parked"),
    [
        ("X" * USER_TEXT_LIMITS.max_message_chars, False),
        ("X" * (USER_TEXT_LIMITS.max_message_chars + 1), True),
        # A wide (CJK) character weighs 1.8 in the token pressure: 8,889 of them reach its limit, 8,890 pass it.
        ("字" * 8_889, False),
        ("字" * 8_890, True),
    ],
)
def test_the_size_check_and_the_engine_draw_the_line_at_the_same_place(tmp_path: Path, text: str, parked: bool) -> None:
    res = ContextBombDefenseService.process_incoming_content(text, workspace_root=tmp_path, kept=True)

    assert ContextBombDefenseService.is_oversized(text) is parked
    assert res.is_spilled is parked


def test_sweep_removes_only_transient_files_older_than_the_ttl(tmp_path: Path) -> None:
    spill_dir = tmp_path / TRANSIENT_SPILLOVER_DIR
    spill_dir.mkdir(parents=True)
    fresh = spill_dir / "payload_fresh.md"
    fresh.write_text("fresh")
    stale = spill_dir / "payload_stale.md"
    stale.write_text("stale")
    past_time = time.time() - 200
    os.utime(stale, (past_time, past_time))
    kept_dir = tmp_path / KEPT_SPILLOVER_DIR
    kept_dir.mkdir(parents=True)
    kept = kept_dir / "payload_kept.md"
    kept.write_text("a person's paste")
    os.utime(kept, (past_time, past_time))

    purged = ContextBombDefenseService.sweep_stale_spillover_files(tmp_path, ttl_seconds=10)

    assert purged == 1
    assert fresh.exists()
    assert not stale.exists()
    assert kept.exists()
