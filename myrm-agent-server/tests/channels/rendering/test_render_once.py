"""A message that carries a rendered chunk is delivered as it is: ``render`` never decorates it twice."""

from __future__ import annotations

import pytest

from app.channels.rendering.renderer import mark_rendered, render
from app.channels.types import OutboundMessage, RenderStyle, ToolStep, ToolSummaryDisplay

_SOURCES = [{"url": "https://example.com/a", "title": "Alpha", "index": 1}]
_STEPS = (ToolStep(name="web_search", label="Searched the web"), ToolStep(name="bash", label="Ran code"))

_STYLES = {
    "markdown": RenderStyle(format="markdown", tool_summary_display=ToolSummaryDisplay.COMPACT),
    "mrkdwn": RenderStyle(format="mrkdwn", tool_summary_display=ToolSummaryDisplay.COMPACT),
    "plaintext": RenderStyle(format="plaintext", tool_summary_display=ToolSummaryDisplay.DETAILED),
}


def _reply(content: str, **overrides: object) -> OutboundMessage:
    fields: dict[str, object] = {
        "channel": "test",
        "recipient_id": "chat-1",
        "content": content,
        "user_id": "u1",
        "tool_steps": _STEPS,
        "metadata": {"sources": _SOURCES, "job_name": "Daily digest", "success": True},
    }
    fields.update(overrides)
    return OutboundMessage(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize("style", _STYLES.values(), ids=_STYLES.keys())
def test_rendering_a_rendered_chunk_changes_nothing(style: RenderStyle) -> None:
    (chunk,) = render(_reply("Answer [1] with a **bold** claim."), style)

    assert render(mark_rendered(_reply("ignored"), chunk), style) == [chunk]


def test_every_chunk_of_a_long_reply_is_delivered_as_rendered() -> None:
    style = RenderStyle(format="markdown", max_text_length=60, tool_summary_display=ToolSummaryDisplay.COMPACT)
    chunks = render(_reply("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda " * 3), style)

    assert len(chunks) > 1
    assert [render(mark_rendered(_reply("ignored"), chunk), style) for chunk in chunks] == [[chunk] for chunk in chunks]


def test_an_unmarked_message_is_still_decorated() -> None:
    """The first render adds the tool summary and sources; only marked messages skip it."""
    style = _STYLES["markdown"]

    (chunk,) = render(_reply("Answer."), style)

    assert "Searched the web" in chunk
    assert "Sources" in chunk


def test_marking_keeps_the_message_and_its_other_metadata() -> None:
    original = _reply("Answer.")

    marked = mark_rendered(original, "chunk")

    assert marked.content == "chunk"
    assert marked.tool_steps == original.tool_steps
    assert marked.recipient_id == original.recipient_id
    assert original.metadata is not None
    assert {key: marked.metadata[key] for key in original.metadata} == original.metadata  # type: ignore[index]
    assert original.content == "Answer."
    assert "rendered" not in str(original.metadata)


def test_a_message_without_metadata_can_be_marked() -> None:
    marked = mark_rendered(_reply("Answer.", metadata=None), "chunk")

    assert render(marked, _STYLES["markdown"]) == ["chunk"]
