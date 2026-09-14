"""Unit tests for Zotero source sync connector."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.wiki.source_sync.schemas import WikiSourceSyncResult  # noqa: F401
from app.services.wiki.source_sync.zotero import (
    _format_creators,
    _render_annotations,
    _render_note,
    sync_zotero_library_to_wiki,
)


def _note(
    *,
    title: str = "T",
    abstract: str = "",
    annotation_lines: list[str] | None = None,
) -> str:
    return _render_note(
        title=title,
        item_type="journalArticle",
        authors=["A B"],
        doi="10.1/x",
        url="https://x",
        year="2024",
        abstract=abstract,
        annotation_lines=annotation_lines or [],
    )


class TestFormatCreators:
    def test_first_last(self) -> None:
        assert _format_creators([{"firstName": "Jane", "lastName": "Doe"}]) == [
            "Jane Doe"
        ]

    def test_single_name(self) -> None:
        assert _format_creators([{"name": "ACM"}]) == ["ACM"]

    def test_skips_non_dict(self) -> None:
        assert _format_creators(["bad", 42]) == []


class TestRenderNote:
    def test_full_note(self) -> None:
        text = _note(abstract="Abs", annotation_lines=["> hi\n> — highlight"])
        assert "## Abstract" in text
        assert "## Annotations" in text
        assert "DOI: `10.1/x`" in text

    def test_minimal_note(self) -> None:
        text = _note()
        assert "## Abstract" not in text
        assert "## Annotations" not in text
        assert "DOI: `10.1/x`" in text


class TestRenderAnnotations:
    def test_highlight_and_note(self) -> None:
        children = [
            {
                "data": {
                    "itemType": "annotation",
                    "annotationType": "highlight",
                    "annotationText": "key finding",
                }
            },
            {
                "data": {
                    "itemType": "annotation",
                    "annotationType": "note",
                    "annotationComment": "my thought",
                }
            },
        ]
        lines = _render_annotations(children)
        assert lines[0].startswith("> key finding")
        assert lines[1] == "- my thought"

    def test_skips_non_annotation_and_empty(self) -> None:
        children = [
            {"data": {"itemType": "note", "note": "regular child note"}},
            {
                "data": {
                    "itemType": "annotation",
                    "annotationType": "highlight",
                    "annotationText": "",
                }
            },
        ]
        assert _render_annotations(children) == []


class TestSyncZoteroLibrary:
    @pytest.mark.asyncio
    async def test_missing_config_fails_fast(self) -> None:
        result = await sync_zotero_library_to_wiki(
            object(),  # type: ignore[arg-type]
            api_key="",
            user_id="",
            max_items=5,
            auto_compile=False,
            compiler_enqueue=None,
        )
        assert result.source == "zotero"
        assert result.failed == 1
        assert "not configured" in result.errors[0]

    @pytest.mark.asyncio
    async def test_invalid_base_url_rejected(self) -> None:
        result = await sync_zotero_library_to_wiki(
            object(),  # type: ignore[arg-type]
            api_key="k",
            user_id="u",
            max_items=5,
            auto_compile=False,
            compiler_enqueue=None,
            base_url="ftp://evil",
        )
        assert result.failed == 1
        assert "invalid zotero base url" in result.errors[0]

    @pytest.mark.asyncio
    async def test_publishes_items_and_counts(self) -> None:
        items = [
            {
                "key": "K1",
                "data": {
                    "itemType": "journalArticle",
                    "title": "Paper One",
                    "abstractNote": "A1",
                    "creators": [{"firstName": "A", "lastName": "B"}],
                    "DOI": "10.1/one",
                    "date": "2024",
                },
            },
            {"key": "K2", "data": {"itemType": "attachment", "title": "pdf"}},
        ]
        publish_result = _publish_result(written=True)
        with (
            patch(
                "app.services.wiki.source_sync.zotero._fetch_top_level_items",
                AsyncMock(return_value=items),
            ),
            patch(
                "app.services.wiki.source_sync.zotero._fetch_annotations",
                AsyncMock(return_value=["- n1"]),
            ),
            patch(
                "app.services.wiki.source_sync.zotero.publish_source_markdown",
                AsyncMock(return_value=publish_result),
            ),
        ):
            result = await sync_zotero_library_to_wiki(
                object(),  # type: ignore[arg-type]
                api_key="k",
                user_id="u",
                max_items=10,
                auto_compile=False,
                compiler_enqueue=None,
            )
        assert result.published == 1
        assert result.skipped == 1

    @pytest.mark.asyncio
    async def test_fetch_error_counts_failed(self) -> None:
        with patch(
            "app.services.wiki.source_sync.zotero._fetch_top_level_items",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = await sync_zotero_library_to_wiki(
                object(),  # type: ignore[arg-type]
                api_key="k",
                user_id="u",
                max_items=5,
                auto_compile=False,
                compiler_enqueue=None,
            )
        assert result.failed == 1
        assert "boom" in result.errors[0]


def _publish_result(*, written: bool) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(
        written=written, conflict_skipped=False, skipped=False, absolute_path="/tmp/x"
    )
