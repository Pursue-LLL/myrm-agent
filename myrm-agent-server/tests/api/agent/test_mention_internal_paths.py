"""Edge-path coverage for the @-mention context builder internals.

[INPUT]
- app.services.agent.params.mention (POS: mention context builder)
- myrm_agent_harness parsers / path security / web fetch (POS: patched collaborators)

[OUTPUT]
- Branch coverage for the refusal, truncation and parser-failure paths of every reference kind

[POS]
The mention builder answers with an XML refusal instead of raising; these tests pin every refusal
branch, so a regression that turns a refusal into an exception (or a silent drop) fails here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agent.params import mention
from app.services.agent.params.models import MentionReferenceRequest

_PATH_SECURITY = "myrm_agent_harness.agent.security.path_security"


def _stored_service(
    *,
    filename: str = "scan.pdf",
    size: int = 2048,
    content: object = b"%PDF-1.4",
) -> SimpleNamespace:
    stored = SimpleNamespace(filename=filename, size=size, storage_path="uploads/f/scan.pdf")
    service = SimpleNamespace(
        get_file_by_id=AsyncMock(return_value=stored),
        get_file_content_by_path=AsyncMock(return_value=content),
    )
    return SimpleNamespace(service=service, ref=MentionReferenceRequest(type="uploaded_file", file_id="f1", label=filename))


class _NoSessionUow:
    """UnitOfWork stand-in whose session is unavailable, so the recall rebuild is skipped."""

    session = None

    async def __aenter__(self) -> "_NoSessionUow":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False


def test_read_file_lines_returns_the_requested_range(tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("\n".join(f"line{i}" for i in range(1, 6)), encoding="utf-8")

    assert mention._read_file_lines(str(path), 2, 3).splitlines() == ["line2", "line3"]
    assert mention._read_file_lines(str(path), 4, None).splitlines() == ["line4", "line5"]


@pytest.mark.parametrize(
    ("raw", "expected_type"),
    [
        ("@diff", "git_diff"),
        ("@codebase", "codebase"),
        ("@folder:src", "workspace_folder"),
        ("@url:https://example.com", "url"),
    ],
)
def test_text_reference_kinds_map_to_structured_types(raw: str, expected_type: str) -> None:
    assert mention._text_reference_to_structured(raw).type == expected_type


def test_text_reference_line_range_swaps_reversed_bounds() -> None:
    ref = mention._text_reference_to_structured("app.py:9-4")

    assert (ref.start_line, ref.end_line) == (4, 9)
    assert mention._text_reference_to_structured("app.py:7").start_line == 7


def test_git_staged_diff_non_zero_exit_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mention.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )

    assert mention._get_git_staged_diff("/tmp") == ""


@pytest.mark.parametrize(
    "failure",
    [subprocess.TimeoutExpired(cmd="git", timeout=30), FileNotFoundError("no git"), RuntimeError("boom")],
)
def test_git_staged_diff_error_paths_return_empty(monkeypatch: pytest.MonkeyPatch, failure: Exception) -> None:
    def _raise(*args: object, **kwargs: object) -> object:
        raise failure

    monkeypatch.setattr(mention.subprocess, "run", _raise)

    assert mention._get_git_staged_diff("/tmp") == ""


def test_folder_tree_returns_empty_for_a_missing_path(tmp_path: Path) -> None:
    assert mention._get_folder_tree(str(tmp_path / "missing"), str(tmp_path)) == ""


def test_folder_tree_truncates_at_the_entry_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    monkeypatch.setattr(mention, "_FOLDER_TREE_MAX_ENTRIES", 1)

    assert "(truncated)" in mention._get_folder_tree(str(tmp_path), str(tmp_path))


def test_folder_tree_survives_a_walk_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _raise(*args: object, **kwargs: object) -> object:
        raise OSError("walk boom")

    monkeypatch.setattr(mention.os, "walk", _raise)

    assert mention._get_folder_tree(str(tmp_path), str(tmp_path)) == ""


@pytest.mark.asyncio
async def test_fetch_url_content_returns_the_page_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Engine:
        async def crawl(self, url: str) -> SimpleNamespace:
            return SimpleNamespace(page_content="  hello  ")

    monkeypatch.setattr("myrm_agent_harness.toolkits.web_fetch.engine.FetchEngine", _Engine)

    assert await mention._fetch_url_content("https://example.com") == "hello"


@pytest.mark.asyncio
async def test_fetch_url_content_returns_empty_when_the_fetch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Engine:
        async def crawl(self, url: str) -> SimpleNamespace:
            raise RuntimeError("blocked")

    monkeypatch.setattr("myrm_agent_harness.toolkits.web_fetch.engine.FetchEngine", _Engine)

    assert await mention._fetch_url_content("https://example.com") == ""


def test_workspace_file_part_denies_a_sensitive_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(f"{_PATH_SECURITY}.is_sensitive_file", lambda path: True)

    part, consumed = mention._workspace_file_part("/tmp/.env", ".env", None, None, 0)

    assert "access denied" in part
    assert consumed == 0


def test_workspace_file_part_survives_a_missing_size(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "note.txt"
    path.write_text("hi", encoding="utf-8")

    def _raise(path: str) -> int:
        raise OSError("stat boom")

    monkeypatch.setattr(mention.os.path, "getsize", _raise)

    part, consumed = mention._workspace_file_part(str(path), "note.txt", None, None, 0)

    assert "hi" in part
    assert consumed > 0


def test_workspace_file_part_rejects_a_line_range_for_an_office_document(tmp_path: Path) -> None:
    path = tmp_path / "report.docx"
    path.write_bytes(b"x")

    part, consumed = mention._workspace_file_part(str(path), "report.docx", 1, 5, 0)

    assert "line range not supported" in part
    assert consumed == 0


def test_workspace_file_part_reports_a_document_too_large_to_inline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "report.docx"
    path.write_bytes(b"x")
    monkeypatch.setattr(mention, "_parse_document", lambda path, ext: "ready")
    monkeypatch.setattr(mention, "_can_inline", lambda *args: False)

    part, consumed = mention._workspace_file_part(str(path), "report.docx", None, None, 0)

    assert "Document too large" in part
    assert consumed == 0


def test_workspace_file_part_reports_content_too_large_to_inline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "note.txt"
    path.write_text("x" * 64, encoding="utf-8")
    monkeypatch.setattr(mention, "_can_inline", lambda *args: False)

    part, consumed = mention._workspace_file_part(str(path), "note.txt", None, None, 0)

    assert "Content too large to inline" in part
    assert consumed == 0


def test_workspace_file_part_reports_a_document_without_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "scan.docx"
    path.write_bytes(b"x")
    monkeypatch.setattr(mention, "_parse_document", lambda path, ext: None)

    part, consumed = mention._workspace_file_part(str(path), "scan.docx", None, None, 0)

    assert "No extractable text" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_stored_file_part_inlines_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = _stored_service(filename="notes.txt", content=b"hello")
    monkeypatch.setattr("app.core.storage.files_service", stored.service)

    part, consumed = await mention._stored_file_part(stored.ref, 0)

    assert "hello" in part
    assert consumed > 0


@pytest.mark.asyncio
async def test_stored_file_part_reports_missing_content(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = _stored_service(content=None)
    monkeypatch.setattr("app.core.storage.files_service", stored.service)

    part, consumed = await mention._stored_file_part(stored.ref, 0)

    assert "file content not found" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_stored_file_part_inlines_an_office_document(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = _stored_service(filename="report.docx", content=b"PK")
    monkeypatch.setattr("app.core.storage.files_service", stored.service)
    monkeypatch.setattr(mention, "_parse_stored_document", AsyncMock(return_value="body"))

    part, consumed = await mention._stored_file_part(stored.ref, 0)

    assert "body" in part
    assert consumed > 0


@pytest.mark.asyncio
async def test_stored_file_part_reports_a_parsed_document_too_large(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = _stored_service(filename="report.docx", content=b"PK")
    monkeypatch.setattr("app.core.storage.files_service", stored.service)
    monkeypatch.setattr(mention, "_parse_stored_document", AsyncMock(return_value="body"))
    monkeypatch.setattr(mention, "_can_inline", lambda *args: False)

    part, consumed = await mention._stored_file_part(stored.ref, 0)

    assert "Document too large" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_stored_file_part_describes_a_binary_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = _stored_service(filename="photo.png", content=b"\x89PNG")
    monkeypatch.setattr("app.core.storage.files_service", stored.service)

    part, consumed = await mention._stored_file_part(stored.ref, 0)

    assert "Binary file" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_stored_file_part_reports_text_too_large_to_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = _stored_service(filename="notes.txt", content=b"x" * 64)
    monkeypatch.setattr("app.core.storage.files_service", stored.service)
    monkeypatch.setattr(mention, "_can_inline", lambda *args: False)

    part, consumed = await mention._stored_file_part(stored.ref, 0)

    assert "Content too large to inline" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_stored_file_part_falls_back_to_binary_when_content_cannot_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = _stored_service(filename="notes.txt", content=SimpleNamespace())
    monkeypatch.setattr("app.core.storage.files_service", stored.service)

    part, _consumed = await mention._stored_file_part(stored.ref, 0)

    assert "Binary file" in part


@pytest.mark.asyncio
async def test_parse_stored_document_uses_the_office_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mention, "_parse_document", lambda path, ext: "parsed")

    assert await mention._parse_stored_document(b"PK", ".docx", "report.docx") == "parsed"


@pytest.mark.asyncio
async def test_parse_stored_document_survives_an_unlink_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mention, "_parse_document", lambda path, ext: "parsed")

    def _raise(path: str) -> None:
        raise OSError("unlink boom")

    monkeypatch.setattr(mention.os, "unlink", _raise)

    assert await mention._parse_stored_document(b"PK", ".docx", "report.docx") == "parsed"


@pytest.mark.asyncio
async def test_parse_stored_document_returns_none_when_the_parser_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(path: str, ext: str) -> str:
        raise RuntimeError("broken package")

    monkeypatch.setattr(mention, "_parse_document", _boom)

    assert await mention._parse_stored_document(b"PK", ".docx", "report.docx") is None


def test_parse_document_returns_none_when_the_harness_parser_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Parser:
        def _parse_sync(self, path: str) -> str:
            raise RuntimeError("cannot parse")

    monkeypatch.setattr("myrm_agent_harness.toolkits.file_parsers.DocxParser", _Parser)

    assert mention._parse_document("report.docx", ".docx") is None


def test_codebase_overview_skips_dotfiles_and_caps_the_scan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".hidden").write_text("x", encoding="utf-8")
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "b.py").write_text("x", encoding="utf-8")
    monkeypatch.setattr(mention, "_CODEBASE_SCAN_MAX_FILES", 1)

    overview = mention._build_codebase_overview(tmp_path)

    assert "capped at 1 files" in overview
    assert ".hidden" not in overview


@pytest.mark.asyncio
async def test_codebase_overview_part_reports_an_unavailable_workspace() -> None:
    part, consumed = await mention._codebase_overview_part("/nonexistent-workspace", 0)

    assert "Workspace unavailable" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_codebase_overview_part_reports_a_truncated_overview(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    monkeypatch.setattr(mention, "_can_inline", lambda *args: False)

    part, consumed = await mention._codebase_overview_part(str(tmp_path), 0)

    assert "codebase-overview" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_wiki_concept_part_reports_a_missing_concept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.wiki.WikiStructure",
        lambda vault_path: SimpleNamespace(resolve_concept_file_path=lambda name: None),
    )

    part, consumed = await mention._wiki_concept_part("ghost", 0)

    assert "concept not found" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_wiki_concept_part_reads_the_concept_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    concept = tmp_path / "concept.md"
    concept.write_text("body", encoding="utf-8")
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.wiki.WikiStructure",
        lambda vault_path: SimpleNamespace(resolve_concept_file_path=lambda name: concept),
    )
    monkeypatch.setattr("app.services.wiki.vault.resolve_wiki_vault_path", lambda agent_id=None: tmp_path)

    part, consumed = await mention._wiki_concept_part("concept", 0)

    assert "body" in part
    assert consumed > 0


@pytest.mark.asyncio
async def test_wiki_concept_part_reports_a_read_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Boom:
        def __init__(self, vault_path: object) -> None:
            raise RuntimeError("vault boom")

    monkeypatch.setattr("myrm_agent_harness.toolkits.wiki.WikiStructure", _Boom)

    part, consumed = await mention._wiki_concept_part("concept", 0)

    assert "read failed" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_prior_chat_part_reports_a_missing_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.chat.chat_crud._ChatCrudMixin.get_chat_metadata", AsyncMock(return_value=None)
    )

    part, consumed = await mention._prior_chat_part("chat-1", "@chat:chat-1", 0)

    assert "chat not found" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_prior_chat_part_reports_a_missing_recall_index(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = SimpleNamespace(is_incognito=False, source="telegram", title="T")
    monkeypatch.setattr(
        "app.services.chat.chat_crud._ChatCrudMixin.get_chat_metadata", AsyncMock(return_value=chat)
    )
    monkeypatch.setattr(mention, "_load_prior_chat_document", AsyncMock(return_value=None))
    monkeypatch.setattr("app.database.repositories.uow.UnitOfWork", _NoSessionUow)

    part, consumed = await mention._prior_chat_part("chat-1", "@chat:chat-1", 0)

    assert "recall index unavailable" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_prior_chat_part_reports_an_excluded_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = SimpleNamespace(is_incognito=False, source="telegram", title="T")
    row = SimpleNamespace(is_excluded=True, title="T", summary="", snippet="")
    monkeypatch.setattr(
        "app.services.chat.chat_crud._ChatCrudMixin.get_chat_metadata", AsyncMock(return_value=chat)
    )
    monkeypatch.setattr(mention, "_load_prior_chat_document", AsyncMock(return_value=row))

    part, consumed = await mention._prior_chat_part("chat-1", "@chat:chat-1", 0)

    assert "excluded from recall" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_prior_chat_part_inlines_summary_and_snippet(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = SimpleNamespace(is_incognito=False, source="telegram", title="T")
    row = SimpleNamespace(is_excluded=False, title="T", summary="sum", snippet="snip")
    monkeypatch.setattr(
        "app.services.chat.chat_crud._ChatCrudMixin.get_chat_metadata", AsyncMock(return_value=chat)
    )
    monkeypatch.setattr(mention, "_load_prior_chat_document", AsyncMock(return_value=row))

    part, consumed = await mention._prior_chat_part("chat-1", "@chat:chat-1", 0)

    assert "summary: sum" in part
    assert "snippet: snip" in part
    assert consumed > 0


@pytest.mark.asyncio
async def test_prior_chat_part_reports_context_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = SimpleNamespace(is_incognito=False, source="telegram", title="T")
    row = SimpleNamespace(is_excluded=False, title="T", summary="sum", snippet="snip")
    monkeypatch.setattr(
        "app.services.chat.chat_crud._ChatCrudMixin.get_chat_metadata", AsyncMock(return_value=chat)
    )
    monkeypatch.setattr(mention, "_load_prior_chat_document", AsyncMock(return_value=row))
    monkeypatch.setattr(mention, "_can_inline", lambda *args: False)

    part, consumed = await mention._prior_chat_part("chat-1", "@chat:chat-1", 0)

    assert "Context too large" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_prior_chat_part_refuses_an_incognito_web_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = SimpleNamespace(is_incognito=True, source="web", title="T")
    monkeypatch.setattr(
        "app.services.chat.chat_crud._ChatCrudMixin.get_chat_metadata", AsyncMock(return_value=chat)
    )

    part, _consumed = await mention._prior_chat_part("chat-1", "@chat:chat-1", 0)

    assert "incognito chats cannot be referenced" in part


@pytest.mark.asyncio
async def test_prior_chat_part_rebuilds_the_recall_index_once(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = SimpleNamespace(is_incognito=False, source="telegram", title="T")
    row = SimpleNamespace(is_excluded=False, title="T", summary="sum", snippet="snip")
    rebuild = AsyncMock()
    lookups = AsyncMock(side_effect=[None, row])

    class _Uow:
        session = SimpleNamespace()

        async def __aenter__(self) -> "_Uow":
            return self

        async def __aexit__(self, *args: object) -> bool:
            return False

    monkeypatch.setattr(
        "app.services.chat.chat_crud._ChatCrudMixin.get_chat_metadata", AsyncMock(return_value=chat)
    )
    monkeypatch.setattr("app.database.repositories.uow.UnitOfWork", _Uow)
    monkeypatch.setattr(
        "app.database.repositories.conversation_recall.lookup_repo.ConversationRecallLookupRepository.fetch_prior_chat_document",
        lookups,
    )
    monkeypatch.setattr(
        "app.services.chat.conversation_recall_index_service.ConversationRecallIndexService.rebuild_chat",
        rebuild,
    )

    part, consumed = await mention._prior_chat_part("chat-1", "@chat:chat-1", 0)

    rebuild.assert_awaited_once()
    assert consumed > 0
    assert "summary: sum" in part


def test_stored_file_part_reports_a_reference_without_a_file_id() -> None:
    ref = MentionReferenceRequest(type="uploaded_file", label="scan.pdf")

    import asyncio

    part, consumed = asyncio.run(mention._stored_file_part(ref, 0))

    assert "missing file_id" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_stored_file_part_reports_a_vanished_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    service = SimpleNamespace(get_file_by_id=AsyncMock(return_value=None), get_file_content_by_path=AsyncMock())
    monkeypatch.setattr("app.core.storage.files_service", service)
    ref = MentionReferenceRequest(type="uploaded_file", file_id="gone", label="scan.pdf")

    part, consumed = await mention._stored_file_part(ref, 0)

    assert "file not found" in part
    assert consumed == 0


@pytest.mark.asyncio
async def test_folder_tree_truncates_inside_the_directory_walk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    monkeypatch.setattr(mention, "_FOLDER_TREE_MAX_ENTRIES", 1)

    assert "(truncated)" in mention._get_folder_tree(str(tmp_path), str(tmp_path))


def _context_refs(*refs: MentionReferenceRequest) -> list[MentionReferenceRequest]:
    return list(refs)


@pytest.mark.asyncio
async def test_context_reports_a_staged_diff_too_large(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mention, "_get_git_staged_diff", lambda workspace: "x" * 32)
    monkeypatch.setattr(mention, "_MENTION_MAX_TOTAL_BYTES", 1)

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="git_staged", label="@staged")), str(tmp_path)
    )

    assert "Diff too large" in part


@pytest.mark.asyncio
async def test_context_inlines_an_unstaged_diff(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        mention.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="diff --git a b\n+x", stderr=""),
    )

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="git_diff", label="@diff")), str(tmp_path)
    )

    assert "git-diff" in part
    assert "+x" in part


@pytest.mark.asyncio
async def test_context_reports_an_unstaged_diff_too_large(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        mention.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="x" * 32, stderr=""),
    )
    monkeypatch.setattr(mention, "_MENTION_MAX_TOTAL_BYTES", 1)

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="git_diff", label="@diff")), str(tmp_path)
    )

    assert "Diff too large" in part


@pytest.mark.asyncio
async def test_context_reports_a_failed_unstaged_diff(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _raise(*args: object, **kwargs: object) -> object:
        raise RuntimeError("git boom")

    monkeypatch.setattr(mention.subprocess, "run", _raise)

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="git_diff", label="@diff")), str(tmp_path)
    )

    assert 'error="git diff failed"' in part


@pytest.mark.asyncio
async def test_context_reports_a_folder_outside_the_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _raise(base: object, rel: object) -> object:
        raise ValueError("outside")

    monkeypatch.setattr(f"{_PATH_SECURITY}.safe_join_path", _raise)

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="workspace_folder", path="../etc", label="@folder:../etc")),
        str(tmp_path),
    )

    assert "path outside workspace" in part


@pytest.mark.asyncio
async def test_context_denies_a_sensitive_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    folder = tmp_path / "secrets"
    folder.mkdir()
    monkeypatch.setattr(f"{_PATH_SECURITY}.is_sensitive_file", lambda path: True)

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="workspace_folder", path="secrets", label="@folder:secrets")),
        str(tmp_path),
    )

    assert "access denied" in part


@pytest.mark.asyncio
async def test_context_reports_a_folder_tree_too_large(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    folder = tmp_path / "src"
    folder.mkdir()
    (folder / "a.py").write_text("x", encoding="utf-8")
    monkeypatch.setattr(mention, "_MENTION_MAX_TOTAL_BYTES", 1)

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="workspace_folder", path="src", label="@folder:src")),
        str(tmp_path),
    )

    assert "Tree too large" in part


@pytest.mark.asyncio
async def test_context_reports_url_content_too_large(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mention, "_fetch_url_content", AsyncMock(return_value="x" * 32))
    monkeypatch.setattr(mention, "_MENTION_MAX_TOTAL_BYTES", 1)

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="url", url="https://example.com", label="@url:example")),
        str(tmp_path),
    )

    assert "Content too large" in part


@pytest.mark.asyncio
async def test_context_reports_a_failed_url_fetch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mention, "_fetch_url_content", AsyncMock(return_value=""))

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="url", url="https://example.com", label="@url:example")),
        str(tmp_path),
    )

    assert "failed to fetch URL" in part


@pytest.mark.asyncio
async def test_context_inlines_url_content(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mention, "_fetch_url_content", AsyncMock(return_value="page text"))

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="url", url="https://example.com", label="@url:example")),
        str(tmp_path),
    )

    assert "page text" in part


@pytest.mark.asyncio
async def test_context_requires_a_workspace_file_path(tmp_path: Path) -> None:
    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="workspace_file", label="@file")), str(tmp_path)
    )

    assert "missing path" in part


@pytest.mark.asyncio
async def test_context_rejects_a_workspace_file_outside_the_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _raise(base: object, rel: object) -> object:
        raise ValueError("outside")

    monkeypatch.setattr(f"{_PATH_SECURITY}.safe_join_path", _raise)

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="workspace_file", path="../etc/passwd", label="passwd")),
        str(tmp_path),
    )

    assert "path outside workspace" in part


@pytest.mark.asyncio
async def test_context_resolves_stored_upload_references(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mention, "_stored_file_part", AsyncMock(return_value=("<part>stored</part>", 7)))

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="uploaded_file", file_id="f1", label="scan.pdf")), str(tmp_path)
    )

    assert "stored" in part


@pytest.mark.asyncio
async def test_context_reports_a_wiki_concept_without_a_name(tmp_path: Path) -> None:
    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="wiki_concept")), str(tmp_path)
    )

    assert "missing concept_name" in part


@pytest.mark.asyncio
async def test_context_resolves_a_wiki_concept(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mention, "_wiki_concept_part", AsyncMock(return_value=("<part>concept</part>", 3)))

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="wiki_concept", concept_name="c", label="@wiki:c")), str(tmp_path)
    )

    assert "concept" in part


@pytest.mark.asyncio
async def test_context_requires_a_wiki_raw_file_id(tmp_path: Path) -> None:
    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="wiki_raw_file", label="@raw")), str(tmp_path)
    )

    assert "missing file_id or path" in part


@pytest.mark.asyncio
async def test_context_resolves_a_wiki_raw_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mention, "_wiki_raw_file_part", AsyncMock(return_value=("<part>raw</part>", 3)))

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="wiki_raw_file", file_id="notes.md", label="@raw:notes")),
        str(tmp_path),
    )

    assert "raw" in part


@pytest.mark.asyncio
async def test_context_requires_a_prior_chat_id(tmp_path: Path) -> None:
    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="prior_chat", label="@chat")), str(tmp_path)
    )

    assert "missing chat_id" in part


@pytest.mark.asyncio
async def test_context_resolves_a_prior_chat(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mention, "_prior_chat_part", AsyncMock(return_value=("<part>chat</part>", 3)))

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="prior_chat", path="chat-1", label="@chat:chat-1")),
        str(tmp_path),
    )

    assert "chat" in part


@pytest.mark.asyncio
async def test_context_reports_an_empty_artifact_selection(tmp_path: Path) -> None:
    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="artifact_range", label="selection", range="1-2")), str(tmp_path)
    )

    assert "empty selection" in part


@pytest.mark.asyncio
async def test_context_inlines_an_artifact_selection(tmp_path: Path) -> None:
    part, _warnings, total_bytes = await mention._build_mention_reference_context(
        _context_refs(
            MentionReferenceRequest(type="artifact_range", content="chosen lines", label="selection", range="1-2")
        ),
        str(tmp_path),
    )

    assert "chosen lines" in part
    assert total_bytes > 0


@pytest.mark.asyncio
async def test_context_reports_an_artifact_selection_too_large(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(mention, "_can_inline", lambda *args: False)

    part, _warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="artifact_range", content="x" * 16, label="selection")),
        str(tmp_path),
    )

    assert "Selection too large" in part


@pytest.mark.asyncio
async def test_context_reports_an_unsupported_reference(tmp_path: Path) -> None:
    ref = MentionReferenceRequest.model_construct(type="mystery", label="mystery")

    part, _warnings, _tokens = await mention._build_mention_reference_context([ref], str(tmp_path))

    assert "unsupported reference" in part


@pytest.mark.asyncio
async def test_context_warns_when_the_hard_token_limit_is_exceeded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    monkeypatch.setattr("myrm_agent_harness.utils.text_utils.get_token_count", lambda text: 100)

    _part, warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="workspace_file", path="note.txt", label="note.txt")),
        str(tmp_path),
        max_context_tokens=100,
    )

    assert warnings and "50% limit" in warnings[0]


@pytest.mark.asyncio
async def test_context_warns_when_the_soft_token_limit_is_exceeded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    monkeypatch.setattr("myrm_agent_harness.utils.text_utils.get_token_count", lambda text: 10)

    _part, warnings, _tokens = await mention._build_mention_reference_context(
        _context_refs(MentionReferenceRequest(type="workspace_file", path="note.txt", label="note.txt")),
        str(tmp_path),
        max_context_tokens=30,
    )

    assert warnings and "25% soft limit" in warnings[0]
