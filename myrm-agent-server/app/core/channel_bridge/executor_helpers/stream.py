"""Channel stream accumulation and progress label translation.

[INPUT]
- app.channels.types::MediaAttachment, ToolStep (POS: Channel message types)

[OUTPUT]
- ShareableArtifact, StreamAccumulator, step_to_label

[POS]
Channel executor 辅助：流式响应累积与 IM 进度标签转换。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from app.channels.types import MediaAttachment, ToolStep

_STEP_LABELS: dict[str, str] = {
    "web_search_tool": "🔍 Searching the web...",
    "reviewing_sources": "📖 Reviewing sources...",
    "code_interpreter_tool": "💻 Running code...",
    "bash_code_execute_tool_tool": "🖥️ Executing command...",
    "file_read_tool": "📄 Reading file...",
    "file_write_tool": "📝 Writing file...",
    "file_edit_tool": "✏️ Editing file...",
}

_SUMMARY_MAX_CHARS = 80


class ShareableArtifact(NamedTuple):
    """Metadata for an artifact eligible for public share link injection."""

    artifact_id: str
    filename: str
    artifact_type: str


@dataclass
class StreamAccumulator:
    """Lightweight accumulator for channel agent responses."""

    chunks: list[str] = field(default_factory=list)
    reasoning_chunks: list[str] = field(default_factory=list)
    tool_steps: list[ToolStep] = field(default_factory=list)
    sources: list[dict[str, object]] = field(default_factory=list)
    error_message: str | None = None
    last_image_base64: str | None = None
    last_image_url: str | None = None
    last_image_mime: str = "image/jpeg"
    last_image_tool: str = ""
    file_attachments: list[MediaAttachment] = field(default_factory=list)
    shareable_artifacts: list[ShareableArtifact] = field(default_factory=list)
    cost_usd: float = 0.0
    model_name: str = ""
    total_tokens: int = 0
    _seen: set[int] = field(default_factory=set)

    def add_sources(self, items: list[dict[str, object]]) -> None:
        for src in items:
            idx = src.get("index")
            if isinstance(idx, int) and idx not in self._seen:
                self._seen.add(idx)
                self.sources.append(src)


def step_to_label(step_key: str, event: dict[str, object]) -> str | None:
    """Translate an Agent step_key into a human-readable progress label."""
    if step_key.endswith("_tool_error"):
        return "⚠️ Tool error, retrying..."

    label = _STEP_LABELS.get(step_key)
    if label:
        if step_key == "reviewing_sources":
            count = event.get("count")
            if isinstance(count, int) and count > 0:
                return f"📖 Reviewing {count} sources..."
            return label
        summary = _extract_input_summary(event.get("data"))
        if summary:
            prefix = label.removesuffix("...").rstrip()
            return f"{prefix}: {summary}"
        return label

    tool_name = str(event.get("tool_name") or "") or step_key.removesuffix("_tool")
    summary = _extract_input_summary(event.get("data"))
    if summary:
        return f"⏳ **{tool_name}** — {summary}"
    return f"⏳ **{tool_name}**"


def _extract_input_summary(data: object) -> str:
    """Extract a concise one-line summary from the step event data field."""
    if not isinstance(data, list) or not data:
        return ""
    first = data[0]
    if not isinstance(first, dict):
        return ""

    raw = (
        first.get("query")
        or first.get("url")
        or first.get("file_path")
        or first.get("code")
        or first.get("skill_name")
        or first.get("text")
        or ""
    )
    if not isinstance(raw, str) or not raw:
        return ""

    one_line = raw.replace("\n", " ").strip()
    if len(one_line) > _SUMMARY_MAX_CHARS:
        return f"{one_line[:_SUMMARY_MAX_CHARS]}…"
    return one_line
