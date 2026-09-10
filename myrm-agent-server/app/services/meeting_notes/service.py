"""Meeting notes orchestration service.

[INPUT]
- app.channels.voice.stt::transcribe (POS: 5-provider STT with fallback)
- app.services.wiki.source_sync.publish_helpers::publish_source_markdown, build_frontmatter (POS: wiki raw publish)
- app.services.wiki.vault.service::get_wiki_archiver (POS: agent wiki vault access)
- app.database.connection::get_session (POS: LLM binding via chat agent)

[OUTPUT]
- process_meeting_audio(): audio file -> chunked parallel transcription -> LLM distillation -> wiki raw publish
- split_audio_into_chunks(): ffmpeg slice plan builder

[POS]
Business orchestration facade for the Meeting Scribe pipeline. Delegates ASR to
channels/voice/stt.py, distillation to the chat agent LLM, and publication to the
wiki raw pipeline. Contains zero ASR/LLM algorithm implementation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.channels.types import VoiceConfig
from app.channels.voice.stt import transcribe
from app.services.meeting_notes.models import (
    MeetingActionItem,
    MeetingNotesResult,
    StructuredMeetingNotes,
    TranscriptChunk,
)

logger = logging.getLogger(__name__)

_CHUNK_SECONDS = 600
_MAX_PARALLEL_ASR = 3
_WIKI_SOURCE_DIR = "meeting-notes"

_FFPROBE_DURATION_RE = re.compile(r"duration=(\d+(?:\.\d+)?)")
_FFMPEG_TS_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _resolve_ffmpeg_binaries() -> tuple[str, str]:
    """Resolve (ffmpeg, ffprobe) executables: env override -> PATH -> imageio-ffmpeg fallback.

    imageio-ffmpeg ships only an ffmpeg binary; when falling back, both probe and
    slice operations route through ffmpeg (no separate ffprobe available).
    """
    env_ffmpeg = os.environ.get("MYRM_FFMPEG_PATH")
    if env_ffmpeg and Path(env_ffmpeg).is_file():
        return env_ffmpeg, env_ffmpeg
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        ffprobe = shutil.which("ffprobe") or ffmpeg
        return ffmpeg, ffprobe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe(), imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg", "ffprobe"


_FFMPEG_BIN, _FFPROBE_BIN = _resolve_ffmpeg_binaries()

_SUMMARY_PROMPT_TEMPLATE = """You are a meeting-minutes extraction engine.
Given the full transcript of a meeting, produce:
1. A concise title (<=60 chars).
2. A 3-5 sentence summary.
3. Decisions made (bullets).
4. Key debate points (bullets).
5. Action items with optional owner and due hint.

Transcript:
{transcript}

Return strict JSON with keys: title, summary, decisions, debate_points,
action_items (array of {{description, owner, due_hint}}). No markdown fences."""


async def _probe_duration(path: Path) -> float:
    """Return audio duration in seconds via ffprobe (0.0 when unavailable)."""
    proc = await asyncio.create_subprocess_exec(
        _FFMPEG_BIN,
        "-i",
        str(path),
        "-f",
        "null",
        "-",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    text = stderr.decode(errors="replace")
    match = _FFPROBE_DURATION_RE.search(text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return 0.0
    ts = _FFMPEG_TS_DURATION_RE.search(text)
    if ts:
        hours, minutes, seconds = ts.group(1), ts.group(2), ts.group(3)
        try:
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        except ValueError:
            return 0.0
    return 0.0


def build_chunk_plan(
    total_seconds: float, chunk_seconds: int = _CHUNK_SECONDS
) -> list[tuple[float, float]]:
    """Build [start, end) slice windows covering the whole audio."""
    if total_seconds <= 0:
        return [(0.0, chunk_seconds)]
    plan: list[tuple[float, float]] = []
    start = 0.0
    while start < total_seconds:
        plan.append((start, min(start + chunk_seconds, total_seconds)))
        start += chunk_seconds
    return plan


def _slice_one(path: Path, start: float, end: float, out_dir: Path, index: int) -> Path:
    """Blocking ffmpeg slice executed in the worker thread."""
    out = out_dir / f"chunk_{index:03d}.mp3"
    subprocess.run(
        [
            _FFMPEG_BIN,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(path),
            "-c",
            "copy",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


async def _slice_chunk(
    path: Path, start: float, end: float, out_dir: Path, index: int
) -> Path:
    return await asyncio.to_thread(_slice_one, path, start, end, out_dir, index)


async def _transcribe_chunk(path: Path, config: VoiceConfig) -> str:
    result = await transcribe(path, config)
    return result.text if result else ""


async def process_meeting_audio(
    audio_path: Path,
    *,
    voice_config: VoiceConfig,
    llm: object,  # BaseChatModel; typed loosely to avoid circular import in orchestration layer
    structure: object,  # WikiStructure from harness wiki compiler
    agent_id: str | None = None,
    chunk_seconds: int = _CHUNK_SECONDS,
    max_parallel: int = _MAX_PARALLEL_ASR,
    auto_compile: bool = True,
    compiler_enqueue: object | None = None,
) -> MeetingNotesResult:
    """Run the full meeting scribe pipeline for one uploaded audio file."""
    total = await _probe_duration(audio_path)
    plan = build_chunk_plan(total, chunk_seconds)
    with tempfile.TemporaryDirectory(prefix="myrm_meeting_") as tmp:
        tmp_dir = Path(tmp)
        slices = await asyncio.gather(
            *[
                _slice_chunk(audio_path, s, e, tmp_dir, i)
                for i, (s, e) in enumerate(plan)
            ]
        )
        sem = asyncio.Semaphore(max_parallel)

        async def _bounded(p: Path) -> str:
            async with sem:
                return await _transcribe_chunk(p, voice_config)

        texts = await asyncio.gather(*[_bounded(p) for p in slices])

    chunks = [
        TranscriptChunk(index=i, start_seconds=s, end_seconds=e, text=t)
        for i, (s, e), t in zip(range(len(plan)), plan, texts, strict=True)
    ]
    transcript = "\n".join(
        f"[{int(c.start_seconds // 60):02d}:{int(c.start_seconds % 60):02d}] {c.text}"
        for c in chunks
        if c.text
    )
    notes = await _distill_notes(transcript, llm)
    published = await _publish_to_wiki(
        structure, notes, transcript, agent_id, auto_compile, compiler_enqueue
    )
    return MeetingNotesResult(
        chunk_count=len(chunks),
        duration_seconds=total,
        notes=notes,
        published_wiki_paths=published,
        language=None,
    )


async def _distill_notes(transcript: str, llm: object) -> StructuredMeetingNotes:
    """LLM-distill decisions/debates/action items from transcript."""
    import json

    if llm is None:
        return StructuredMeetingNotes(title="Meeting Notes", summary=transcript[:4000])
    prompt = _SUMMARY_PROMPT_TEMPLATE.format(transcript=transcript[:120000])
    response = await llm.ainvoke(prompt)  # type: ignore[attr-defined]
    content = getattr(response, "content", str(response))
    try:
        payload = json.loads(
            str(content).strip().removeprefix("```json").removesuffix("```").strip()
        )
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "Meeting notes LLM response was not valid JSON; falling back to raw summary"
        )
        return StructuredMeetingNotes(
            title="Meeting Notes", summary=str(content)[:4000]
        )
    action_items = tuple(
        MeetingActionItem(
            description=str(item.get("description", "")),
            owner=item.get("owner") or None,
            due_hint=item.get("due_hint") or None,
        )
        for item in payload.get("action_items", [])
        if isinstance(item, dict) and item.get("description")
    )
    return StructuredMeetingNotes(
        title=str(payload.get("title", "Meeting Notes"))[:80],
        summary=str(payload.get("summary", "")),
        decisions=tuple(str(d) for d in payload.get("decisions", [])),
        debate_points=tuple(str(d) for d in payload.get("debate_points", [])),
        action_items=action_items,
    )


def _render_minutes_markdown(
    notes: StructuredMeetingNotes, transcript: str, duration_seconds: float
) -> str:
    """Render structured notes + transcript into wiki-ready Markdown body."""
    lines: list[str] = [f"# {notes.title}", "", "## Summary", notes.summary, ""]
    if notes.decisions:
        lines += ["## Decisions", *[f"- {d}" for d in notes.decisions], ""]
    if notes.debate_points:
        lines += ["## Key Debate Points", *[f"- {p}" for p in notes.debate_points], ""]
    if notes.action_items:
        lines += ["## Action Items"]
        lines += [
            f"- [ ] {item.description} (owner: {item.owner or 'TBD'}, due: {item.due_hint or 'TBD'})"
            for item in notes.action_items
        ]
        lines.append("")
    lines += ["## Transcript", transcript]
    return "\n".join(lines)


async def _publish_to_wiki(
    structure: object,
    notes: StructuredMeetingNotes,
    transcript: str,
    agent_id: str | None,
    auto_compile: bool,
    compiler_enqueue: object | None,
) -> list[str]:
    """Publish minutes markdown into the wiki raw pipeline; returns published paths."""
    from app.services.wiki.source_sync.publish_helpers import (
        build_frontmatter,
        publish_source_markdown,
        sanitize_path_segment,
    )

    title = notes.title or "Meeting Notes"
    slug = sanitize_path_segment(f"meeting-{title}")
    relative_path = f"{_WIKI_SOURCE_DIR}/{slug}.md"
    content = (
        build_frontmatter(
            source="meeting_notes",
            title=title,
            external_id=f"meeting:{slug}",
            extra={"type": "meeting-notes"},
        )
        + "\n"
        + _render_minutes_markdown(notes, transcript, 0.0)
    )
    published = await publish_source_markdown(
        structure,  # type: ignore[arg-type]
        relative_path=relative_path,
        content=content,
        auto_compile=auto_compile,
        compiler_enqueue=compiler_enqueue,
    )
    return [str(published)] if published else []
