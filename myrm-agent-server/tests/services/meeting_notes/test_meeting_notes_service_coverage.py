"""Coverage tests for the meeting-notes orchestration service (mocked external I/O).

Exercises the distillation fallbacks, the wiki publish path and the collision-free
note path with deterministic mocks so the module stays at production coverage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.meeting_notes import service as svc_mod  # noqa: E402
from app.services.meeting_notes.models import StructuredMeetingNotes  # noqa: E402


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    async def ainvoke(self, _prompt: str) -> _FakeResponse:
        return _FakeResponse(self._content)


def _raw_publish_result(relative_path: str, *, written: bool, security_blocked: bool = False) -> Any:
    """Build the real harness result object so mocks cannot drift from the contract."""
    from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import RawPublishResult

    return RawPublishResult(
        relative_path=relative_path,
        absolute_path=Path("/tmp/e2e") / relative_path,
        content_hash="0" * 64,
        written=written,
        skipped=not written,
        superseded=False,
        created=written,
        security_verdict="blocked" if security_blocked else "clean",
        security_blocked=security_blocked,
    )


async def test_distill_none_llm_returns_raw_summary() -> None:
    notes = await svc_mod.distill_meeting_notes("raw transcript", None)
    assert notes.summary == "raw transcript"


async def test_distill_invalid_json_falls_back() -> None:
    notes = await svc_mod.distill_meeting_notes("raw", _FakeLLM("not-json"))

    assert notes.summary == "not-json"


async def test_distill_valid_json_parses_risks() -> None:
    content = (
        '{"title":"T","summary":"S","decisions":["d"],"debate_points":["p"],'
        '"risks":["r"],"action_items":[{"description":"a","owner":"Bob","due_hint":"Fri"}]}'
    )
    notes = await svc_mod.distill_meeting_notes("raw", _FakeLLM(content))
    assert notes.risks == ("r",)
    assert notes.action_items[0].owner == "Bob"


@pytest.mark.parametrize("field", ["decisions", "debate_points", "risks"])
async def test_distill_single_string_field_becomes_one_entry(field: str) -> None:
    """LLMs return a bare string for a one-item list; it must not explode per character."""
    notes = await svc_mod.distill_meeting_notes(
        "raw", _FakeLLM(json.dumps({"title": "T", "summary": "S", field: "vendor contract expired"}))
    )
    assert getattr(notes, field) == ("vendor contract expired",)


@pytest.mark.parametrize("field", ["decisions", "debate_points", "risks", "action_items"])
async def test_distill_null_field_degrades_to_empty(field: str) -> None:
    """`null` means "no items"; it must never raise and lose the whole meeting."""
    notes = await svc_mod.distill_meeting_notes(
        "raw", _FakeLLM(json.dumps({"title": "T", "summary": "S", field: None}))
    )
    assert getattr(notes, field) == ()


async def test_distill_null_title_falls_back_to_default() -> None:
    notes = await svc_mod.distill_meeting_notes(
        "raw", _FakeLLM(json.dumps({"title": None, "summary": "S"}))
    )
    assert notes.title == "Meeting Notes"
    assert notes.title != "None"


@pytest.mark.parametrize("raw", ['["not","an","object"]', "42", '"plain string"', "null"])
async def test_distill_non_object_payload_falls_back_to_raw_summary(raw: str) -> None:
    """A JSON scalar/list is not a minutes object: degrade, never 500."""
    notes = await svc_mod.distill_meeting_notes("raw", _FakeLLM(raw))
    assert notes.summary == raw
    assert notes.risks == ()
    assert notes.action_items == ()


async def test_distill_action_items_accepts_shapes_llms_actually_emit() -> None:
    """Mixed shapes must all yield usable action items instead of raising or vanishing."""
    notes = await svc_mod.distill_meeting_notes(
        "raw",
        _FakeLLM(
            json.dumps(
                {
                    "title": "T",
                    "summary": "S",
                    "action_items": [
                        "draft the checklist",
                        {"description": "  sign the contract  ", "owner": "", "due_hint": None},
                        {"owner": "no description"},
                        42,
                    ],
                }
            )
        ),
    )
    assert [item.description for item in notes.action_items] == [
        "draft the checklist",
        "sign the contract",
    ]
    assert notes.action_items[1].owner is None
    assert notes.action_items[1].due_hint is None


async def test_distill_single_action_item_object_is_wrapped() -> None:
    notes = await svc_mod.distill_meeting_notes(
        "raw",
        _FakeLLM(json.dumps({"title": "T", "summary": "S", "action_items": {"description": "only one"}})),
    )
    assert [item.description for item in notes.action_items] == ["only one"]


async def test_distill_strips_blank_entries_and_truncates_title() -> None:
    notes = await svc_mod.distill_meeting_notes(
        "raw",
        _FakeLLM(
            json.dumps(
                {
                    "title": "T" * 200,
                    "summary": "S",
                    "risks": ["  ", "", "real risk", "   "],
                }
            )
        ),
    )
    assert len(notes.title) == 80
    assert notes.risks == ("real risk",)


async def test_publish_meeting_notes_renders_risks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from myrm_agent_harness.toolkits.wiki import WikiStructure

    structure = WikiStructure(base_dir=tmp_path)
    captured: dict[str, Any] = {}

    async def _fake_publish(structure: object, *, relative_path: str, content: str, **_kwargs: object) -> Any:
        captured["content"] = content
        captured["relative_path"] = relative_path
        return _raw_publish_result(relative_path, written=True)

    monkeypatch.setattr(svc_mod, "publish_source_markdown", _fake_publish)
    monkeypatch.setattr(svc_mod, "build_frontmatter", lambda **_kwargs: "---\n")
    monkeypatch.setattr(svc_mod, "sanitize_path_segment", lambda segment: segment)

    notes = StructuredMeetingNotes(title="Plan", summary="S", risks=("Vendor lock-in",))
    published = await svc_mod.publish_meeting_notes(structure, notes, "[00:00] hi", True, None)

    assert "## Risks" in captured["content"]
    assert captured["relative_path"].startswith("meeting-notes/")
    assert published == [captured["relative_path"]]


async def test_publish_meeting_notes_skips_unwritten_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A blocked/skipped publish must not be reported as a published path."""
    from myrm_agent_harness.toolkits.wiki import WikiStructure

    structure = WikiStructure(base_dir=tmp_path)

    async def _fake_publish(structure: object, *, relative_path: str, content: str, **_kwargs: object) -> Any:
        return _raw_publish_result(relative_path, written=False, security_blocked=True)

    monkeypatch.setattr(svc_mod, "publish_source_markdown", _fake_publish)
    monkeypatch.setattr(svc_mod, "build_frontmatter", lambda **_kwargs: "---\n")
    monkeypatch.setattr(svc_mod, "sanitize_path_segment", lambda segment: segment)

    notes = StructuredMeetingNotes(title="Plan", summary="S", risks=("r",))
    assert await svc_mod.publish_meeting_notes(structure, notes, "t", False, None) == []


def test_free_meeting_note_path_suffixes_on_collision(tmp_path: Path) -> None:
    """A repeated LLM title must not silently drop the meeting deliverable."""
    from myrm_agent_harness.toolkits.wiki import WikiStructure

    structure = WikiStructure(base_dir=tmp_path)
    assert svc_mod._free_meeting_note_path(structure, "meeting-Plan") == "meeting-notes/meeting-Plan.md"

    (tmp_path / "raw" / "meeting-notes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "raw" / "meeting-notes" / "meeting-Plan.md").write_text("x", encoding="utf-8")
    assert svc_mod._free_meeting_note_path(structure, "meeting-Plan") == "meeting-notes/meeting-Plan-2.md"

    (tmp_path / "raw" / "meeting-notes" / "meeting-Plan-2.md").write_text("x", encoding="utf-8")
    assert svc_mod._free_meeting_note_path(structure, "meeting-Plan") == "meeting-notes/meeting-Plan-3.md"


def test_render_minutes_markdown_includes_risks() -> None:
    from app.services.meeting_notes.models import MeetingActionItem

    notes = StructuredMeetingNotes(
        title="Weekly",
        summary="S",
        decisions=("d",),
        debate_points=("p",),
        risks=("Vendor lock-in",),
        action_items=(MeetingActionItem(description="a", owner="Bob", due_hint="Fri"),),
    )
    body = svc_mod._render_minutes_markdown(notes, "t")
    assert "## Risks" in body and "Vendor lock-in" in body
