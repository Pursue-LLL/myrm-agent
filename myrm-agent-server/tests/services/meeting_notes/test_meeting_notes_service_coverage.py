"""Coverage tests for the meeting-notes orchestration service (mocked external I/O).

Exercises the ffmpeg/probe/slice orchestration, distillation fallbacks, and wiki
publish path with deterministic mocks so the module stays at production coverage.
"""

from __future__ import annotations

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


def test_resolve_ffmpeg_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    binary = tmp_path / "ffmpeg"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("MYRM_FFMPEG_PATH", str(binary))
    assert svc_mod._resolve_ffmpeg_binaries() == (str(binary), str(binary))


def test_resolve_ffmpeg_from_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MYRM_FFMPEG_PATH", raising=False)
    monkeypatch.setattr(
        svc_mod.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in {"ffmpeg", "ffprobe"} else None,
    )
    assert svc_mod._resolve_ffmpeg_binaries() == ("/usr/bin/ffmpeg", "/usr/bin/ffprobe")


async def test_probe_duration_parses_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Proc:
        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b"Duration: 00:02:05.50, start: 0.0"

    async def _fake_exec(*_args: object, **_kwargs: object) -> _Proc:
        return _Proc()

    monkeypatch.setattr(svc_mod.asyncio, "create_subprocess_exec", _fake_exec)
    assert await svc_mod._probe_duration(Path("x.mp3")) == pytest.approx(125.5)


async def test_probe_duration_parses_keyed_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Proc:
        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b"foo duration=42.25 bar"

    async def _fake_exec(*_args: object, **_kwargs: object) -> _Proc:
        return _Proc()

    monkeypatch.setattr(svc_mod.asyncio, "create_subprocess_exec", _fake_exec)
    assert await svc_mod._probe_duration(Path("x.mp3")) == pytest.approx(42.25)


async def test_probe_duration_unavailable_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Proc:
        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b"no duration here"

    async def _fake_exec(*_args: object, **_kwargs: object) -> _Proc:
        return _Proc()

    monkeypatch.setattr(svc_mod.asyncio, "create_subprocess_exec", _fake_exec)
    assert await svc_mod._probe_duration(Path("x.mp3")) == 0.0


def test_slice_one_builds_ffmpeg_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, list[str]] = {}

    def _fake_run(cmd: list[str], **_kwargs: object) -> None:
        captured["cmd"] = cmd

    monkeypatch.setattr(svc_mod.subprocess, "run", _fake_run)
    out = svc_mod._slice_one(tmp_path / "in.mp3", 10.0, 20.0, tmp_path, 3)
    assert out.name == "chunk_003.mp3"
    assert "-ss" in captured["cmd"] and "10.000" in captured["cmd"]


async def test_slice_chunk_delegates_to_thread(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    expected = tmp_path / "chunk_000.mp3"

    def _fake_slice(*_args: object) -> Path:
        return expected

    monkeypatch.setattr(svc_mod, "_slice_one", _fake_slice)
    assert await svc_mod._slice_chunk(tmp_path / "in.mp3", 0.0, 10.0, tmp_path, 0) == expected


async def test_transcribe_chunk_returns_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _Result:
        text = "hello"

    async def _fake_transcribe(_path: Path, _config: object) -> _Result:
        return _Result()

    monkeypatch.setattr(svc_mod, "transcribe", _fake_transcribe)
    assert await svc_mod._transcribe_chunk(tmp_path / "a.mp3", object()) == "hello"


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


async def test_process_meeting_audio_orchestrates_pipeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _probe(_path: Path) -> float:
        return 1200.0

    async def _slice(_path: Path, _s: float, _e: float, out_dir: Path, index: int) -> Path:
        return out_dir / f"chunk_{index}.mp3"

    async def _transcribe(_path: Path, _config: object) -> str:
        return "text"

    async def _distill(_transcript: str, _llm: object) -> StructuredMeetingNotes:
        return StructuredMeetingNotes(title="T", summary="S", risks=("R",))

    async def _publish(*_args: object, **_kwargs: object) -> list[str]:
        return ["meeting-notes/t.md"]

    monkeypatch.setattr(svc_mod, "_probe_duration", _probe)
    monkeypatch.setattr(svc_mod, "_slice_chunk", _slice)
    monkeypatch.setattr(svc_mod, "_transcribe_chunk", _transcribe)
    monkeypatch.setattr(svc_mod, "distill_meeting_notes", _distill)
    monkeypatch.setattr(svc_mod, "publish_meeting_notes", _publish)

    result = await svc_mod.process_meeting_audio(
        tmp_path / "a.mp3",
        voice_config=object(),  # type: ignore[arg-type]
        llm=object(),
        structure=object(),
        chunk_seconds=600,
    )
    assert result.chunk_count == 2
    assert result.duration_seconds == 1200.0
    assert result.published_wiki_paths == ["meeting-notes/t.md"]


async def test_publish_meeting_notes_renders_risks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.services.wiki.source_sync.publish_helpers as helpers

    captured: dict[str, Any] = {}

    async def _fake_publish(structure: object, *, relative_path: str, content: str, **_kwargs: object) -> str:
        captured["content"] = content
        captured["relative_path"] = relative_path
        return relative_path

    monkeypatch.setattr(helpers, "publish_source_markdown", _fake_publish)
    monkeypatch.setattr(helpers, "build_frontmatter", lambda **_kwargs: "---\n")
    monkeypatch.setattr(helpers, "sanitize_path_segment", lambda segment: segment)

    notes = StructuredMeetingNotes(title="Plan", summary="S", risks=("Vendor lock-in",))
    published = await svc_mod.publish_meeting_notes(object(), notes, "[00:00] hi", None, True, None)

    assert "## Risks" in captured["content"]
    assert captured["relative_path"].startswith("meeting-notes/")
    assert published == [captured["relative_path"]]


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
    body = svc_mod._render_minutes_markdown(notes, "t", 0.0)
    assert "## Risks" in body and "Vendor lock-in" in body
