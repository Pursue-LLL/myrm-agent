from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.services.agent.params.models import MentionReferenceRequest


@pytest.mark.asyncio
async def test_workspace_file_reference_inlines_text() -> None:
    from app.services.agent.params.mention import _build_mention_reference_context

    workspace = Path(tempfile.mkdtemp())
    (workspace / "notes.txt").write_text("Hello World")

    context, warnings, tokens = await _build_mention_reference_context(
        [MentionReferenceRequest(type="workspace_file", path="notes.txt", label="@notes.txt")],
        str(workspace),
    )

    assert "<mentioned_files>" in context
    assert 'path="@notes.txt"' in context
    assert 'type="text"' in context
    assert "Hello World" in context
    assert warnings == []
    assert tokens > 0


@pytest.mark.asyncio
async def test_workspace_file_reference_blocks_traversal() -> None:
    from app.services.agent.params.mention import _build_mention_reference_context

    workspace = Path(tempfile.mkdtemp())
    context, warnings, tokens = await _build_mention_reference_context(
        [MentionReferenceRequest(type="workspace_file", path="../../etc/passwd", label="@passwd")],
        str(workspace),
    )

    assert 'error="path outside workspace"' in context
    assert warnings == []
    assert tokens > 0


@pytest.mark.asyncio
async def test_git_diff_reference_is_structured() -> None:
    from app.services.agent.params.mention import _build_mention_reference_context

    workspace = Path(tempfile.mkdtemp())
    context, warnings, tokens = await _build_mention_reference_context(
        [MentionReferenceRequest(type="git_diff", label="@diff")],
        str(workspace),
    )

    assert 'path="@diff"' in context
    assert 'type="git-diff"' in context
    assert warnings == []
    assert tokens > 0

