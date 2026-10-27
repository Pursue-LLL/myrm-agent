"""The stub a spilled payload leaves in the prompt, and the kept spill directory.

A person often writes the request after the pasted text, so the stub must show the end of the
text and tell the model to read the file; the same text spilled twice must give the same stub
and the same single file.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from myrm_agent_harness.agent.context_guard import (
    KEPT_SPILLOVER_DIR,
    TRANSIENT_SPILLOVER_DIR,
    ContextGuardConfig,
    EphemeralTransientSweeper,
    SpilloverEngine,
)

_REQUEST = "Please list every clause that disadvantages the supplier."


def _long_text(request: str = _REQUEST) -> str:
    return "Clause 1. The supplier delivers goods.\n" + ("Filler sentence of the agreement. " * 900) + "\n" + request


def _kept_engine() -> SpilloverEngine:
    return SpilloverEngine(ContextGuardConfig(spillover_dir_name=KEPT_SPILLOVER_DIR))


def test_the_end_of_the_text_stays_visible_so_a_trailing_request_is_not_lost(tmp_path: Path) -> None:
    result = SpilloverEngine().process_content(_long_text(), base_dir=tmp_path)

    assert result.spilled
    assert _REQUEST in result.sanitized_content
    assert "Clause 1. The supplier delivers goods." in result.sanitized_content
    # The middle of the text is what the stub replaces.
    assert result.sanitized_content.count("Filler sentence of the agreement.") < 30


def test_the_stub_tells_the_model_to_read_the_file_and_that_a_bare_paste_is_the_request(tmp_path: Path) -> None:
    stub = SpilloverEngine().process_content(_long_text(), base_dir=tmp_path).sanitized_content

    assert "Read the file with file_read_tool before you answer" in stub
    assert "nothing but the pasted text, the pasted text is the user's request" in stub


def test_a_text_too_short_to_have_a_separate_end_is_not_repeated(tmp_path: Path) -> None:
    engine = SpilloverEngine(ContextGuardConfig(max_message_chars=50, preview_chars=60))
    result = engine.process_content("a" * 80 + " end", base_dir=tmp_path)

    assert result.spilled
    assert "<preview_end>" not in result.sanitized_content
    assert result.sanitized_content.count("a" * 60) == 1


def test_spilling_the_same_text_twice_gives_one_file_and_a_byte_identical_stub(tmp_path: Path) -> None:
    first = _kept_engine().process_content(_long_text(), base_dir=tmp_path)
    second = _kept_engine().process_content(_long_text(), base_dir=tmp_path)

    assert first.sanitized_content == second.sanitized_content
    assert first.payload is not None and second.payload is not None
    assert first.payload.file_path == second.payload.file_path
    assert [p.name for p in (tmp_path / KEPT_SPILLOVER_DIR).glob("*.md")] == [Path(first.payload.file_path).name]


def test_the_same_text_in_two_workspaces_gives_the_same_stub(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    stub_one = _kept_engine().process_content(_long_text(), base_dir=one).sanitized_content
    stub_two = _kept_engine().process_content(_long_text(), base_dir=two).sanitized_content

    assert stub_one == stub_two
    assert str(tmp_path) not in stub_one


def test_different_texts_get_different_files(tmp_path: Path) -> None:
    first = _kept_engine().process_content(_long_text("Question A"), base_dir=tmp_path)
    second = _kept_engine().process_content(_long_text("Question B"), base_dir=tmp_path)

    assert first.payload is not None and second.payload is not None
    assert first.payload.file_path != second.payload.file_path
    assert len(list((tmp_path / KEPT_SPILLOVER_DIR).glob("*.md"))) == 2


def test_the_stub_names_the_file_by_a_workspace_relative_path(tmp_path: Path) -> None:
    result = _kept_engine().process_content(_long_text(), base_dir=tmp_path)

    assert result.payload is not None
    assert re.fullmatch(rf"{re.escape(KEPT_SPILLOVER_DIR)}/payload_[0-9a-f]{{16}}\.md", result.payload.relative_path)
    assert f'path="{result.payload.relative_path}"' in result.sanitized_content


def test_the_spill_directory_ignores_itself_for_version_control(tmp_path: Path) -> None:
    _kept_engine().process_content(_long_text(), base_dir=tmp_path)
    SpilloverEngine().process_content(_long_text(), base_dir=tmp_path)

    assert (tmp_path / KEPT_SPILLOVER_DIR / ".gitignore").read_text(encoding="utf-8") == "*\n"
    assert (tmp_path / TRANSIENT_SPILLOVER_DIR / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_a_kept_spill_survives_the_sweeper_and_a_transient_one_does_not(tmp_path: Path) -> None:
    kept = _kept_engine().process_content(_long_text("kept"), base_dir=tmp_path)
    transient = SpilloverEngine().process_content(_long_text("transient"), base_dir=tmp_path)
    assert kept.payload is not None and transient.payload is not None
    long_ago = time.time() - 25 * 3600
    for spilled in (kept, transient):
        assert spilled.payload is not None
        os.utime(spilled.payload.file_path, (long_ago, long_ago))

    removed = EphemeralTransientSweeper().sweep_directory(tmp_path)

    assert removed == 1
    assert Path(kept.payload.file_path).exists()
    assert not Path(transient.payload.file_path).exists()


def test_spilling_a_text_again_renews_the_age_of_its_transient_file(tmp_path: Path) -> None:
    first = SpilloverEngine().process_content(_long_text(), base_dir=tmp_path)
    assert first.payload is not None
    long_ago = time.time() - 25 * 3600
    os.utime(first.payload.file_path, (long_ago, long_ago))

    SpilloverEngine().process_content(_long_text(), base_dir=tmp_path)

    assert EphemeralTransientSweeper().sweep_directory(tmp_path) == 0
    assert Path(first.payload.file_path).exists()


def test_a_file_that_differs_in_size_is_replaced(tmp_path: Path) -> None:
    first = _kept_engine().process_content(_long_text(), base_dir=tmp_path)
    assert first.payload is not None
    Path(first.payload.file_path).write_text("truncated", encoding="utf-8")

    _kept_engine().process_content(_long_text(), base_dir=tmp_path)

    assert Path(first.payload.file_path).read_text(encoding="utf-8") == _long_text()
