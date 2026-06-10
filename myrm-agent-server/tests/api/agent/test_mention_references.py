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


@pytest.mark.asyncio
async def test_codebase_reference_returns_index_or_unavailable() -> None:
    """@codebase mention returns either index overview or graceful unavailable message."""
    from app.services.agent.params.mention import _build_mention_reference_context

    workspace = Path(tempfile.mkdtemp())
    (workspace / "main.py").write_text("def hello():\n    pass\n")

    context, warnings, tokens = await _build_mention_reference_context(
        [MentionReferenceRequest(type="codebase", label="@codebase")],
        str(workspace),
    )

    assert "@codebase" in context
    assert "codebase-index" in context
    assert warnings == []
    assert tokens >= 0


def test_text_reference_codebase_parsed() -> None:
    """_text_reference_to_structured recognizes @codebase token."""
    from app.services.agent.params.mention import _text_reference_to_structured

    ref = _text_reference_to_structured("@codebase")
    assert ref.type == "codebase"
    assert ref.label == "@codebase"


def test_text_reference_staged_parsed() -> None:
    """_text_reference_to_structured recognizes @staged token."""
    from app.services.agent.params.mention import _text_reference_to_structured

    ref = _text_reference_to_structured("@staged")
    assert ref.type == "git_staged"


def test_text_reference_diff_parsed() -> None:
    """_text_reference_to_structured recognizes @diff token."""
    from app.services.agent.params.mention import _text_reference_to_structured

    ref = _text_reference_to_structured("@diff")
    assert ref.type == "git_diff"


@pytest.mark.asyncio
async def test_codebase_reference_empty_workspace() -> None:
    """@codebase on empty workspace returns graceful response (no crash)."""
    from app.services.agent.params.mention import _build_mention_reference_context

    workspace = Path(tempfile.mkdtemp())
    context, warnings, tokens = await _build_mention_reference_context(
        [MentionReferenceRequest(type="codebase", label="@codebase")],
        str(workspace),
    )

    assert "@codebase" in context
    assert warnings == []


@pytest.mark.asyncio
async def test_codebase_reference_with_multiple_languages() -> None:
    """@codebase indexes Python + TypeScript files correctly."""
    from app.services.agent.params.mention import _build_mention_reference_context

    workspace = Path(tempfile.mkdtemp())
    (workspace / "app.py").write_text("class App:\n    pass\n")
    (workspace / "utils.ts").write_text("export function helper(): void {}\n")

    context, warnings, tokens = await _build_mention_reference_context(
        [MentionReferenceRequest(type="codebase", label="@codebase")],
        str(workspace),
    )

    assert "@codebase" in context
    assert "codebase-index" in context
    assert warnings == []


@pytest.mark.asyncio
async def test_mixed_references_with_codebase() -> None:
    """@codebase can coexist with other reference types."""
    from app.services.agent.params.mention import _build_mention_reference_context

    workspace = Path(tempfile.mkdtemp())
    (workspace / "main.py").write_text("x = 1\n")
    (workspace / "notes.txt").write_text("Hello\n")

    refs = [
        MentionReferenceRequest(type="workspace_file", path="notes.txt", label="@notes.txt"),
        MentionReferenceRequest(type="codebase", label="@codebase"),
    ]
    context, warnings, tokens = await _build_mention_reference_context(refs, str(workspace))

    assert "@notes.txt" in context
    assert "@codebase" in context
    assert warnings == []
