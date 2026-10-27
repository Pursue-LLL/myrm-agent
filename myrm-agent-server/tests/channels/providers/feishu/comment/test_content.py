"""Tests for the text extraction and prompt building behind Feishu document comment turns."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.channels.providers.feishu.api import FeishuClient
from app.channels.providers.feishu.comment.content import (
    _extract_docs_links,
    _extract_reply_text,
    _extract_semantic_text,
    _format_referenced_docs,
    _get_reply_user_id,
    _resolve_wiki_links,
    _select_local_timeline,
    _select_whole_timeline,
    _truncate,
    build_local_comment_prompt,
    build_whole_comment_prompt,
)

# ── Prompt builders ────────────────────────────────────────────


class TestPromptBuilders:
    def test_local_prompt_contains_essentials(self) -> None:
        prompt = build_local_comment_prompt(
            doc_title="My PRD",
            doc_url="https://feishu.cn/doc/abc",
            file_token="abc",
            file_type="docx",
            comment_id="c1",
            quote_text="some quoted text",
            root_comment_text="original comment",
            target_reply_text="user's reply",
            timeline=[("ou_user", "user says hi", False)],
            self_open_id="ou_bot",
            target_index=0,
        )
        assert "My PRD" in prompt
        assert "some quoted text" in prompt
        assert "NO_REPLY" in prompt
        assert "comment_id=c1" in prompt

    def test_whole_prompt_contains_essentials(self) -> None:
        prompt = build_whole_comment_prompt(
            doc_title="Tech Spec",
            doc_url="https://feishu.cn/doc/xyz",
            file_token="xyz",
            file_type="doc",
            comment_text="user's comment",
            timeline=[("ou_user", "hello", False), ("ou_bot", "reply", True)],
            self_open_id="ou_bot",
            current_index=0,
            nearest_self_index=1,
        )
        assert "Tech Spec" in prompt
        assert "whole-document comment" in prompt
        assert "<-- YOU" in prompt


# ── Content extraction coverage ───────────────────────────────


class TestExtractReplyText:
    def test_dict_content(self) -> None:
        reply: dict[str, object] = {
            "content": {
                "elements": [
                    {"type": "text_run", "text_run": {"text": "hello"}},
                    {"type": "docs_link", "docs_link": {"url": "https://x.com"}},
                    {"type": "person", "person": {"user_id": "u1"}},
                ]
            }
        }
        assert _extract_reply_text(reply) == "hellohttps://x.com@u1"

    def test_string_content_json(self) -> None:
        reply: dict[str, object] = {"content": json.dumps({"elements": [{"type": "text_run", "text_run": {"text": "hi"}}]})}
        assert _extract_reply_text(reply) == "hi"

    def test_string_content_invalid_json(self) -> None:
        reply: dict[str, object] = {"content": "plain text"}
        assert _extract_reply_text(reply) == "plain text"

    def test_non_dict_content(self) -> None:
        reply: dict[str, object] = {"content": 42}
        assert _extract_reply_text(reply) == ""

    def test_non_list_elements(self) -> None:
        reply: dict[str, object] = {"content": {"elements": "not_a_list"}}
        assert _extract_reply_text(reply) == ""

    def test_non_dict_element_skipped(self) -> None:
        reply: dict[str, object] = {"content": {"elements": ["not_a_dict"]}}
        assert _extract_reply_text(reply) == ""

    def test_non_dict_text_run(self) -> None:
        reply: dict[str, object] = {"content": {"elements": [{"type": "text_run", "text_run": "bad"}]}}
        assert _extract_reply_text(reply) == ""

    def test_non_dict_docs_link(self) -> None:
        reply: dict[str, object] = {"content": {"elements": [{"type": "docs_link", "docs_link": "bad"}]}}
        assert _extract_reply_text(reply) == ""

    def test_non_dict_person(self) -> None:
        reply: dict[str, object] = {"content": {"elements": [{"type": "person", "person": "bad"}]}}
        assert _extract_reply_text(reply) == ""

    def test_empty_content(self) -> None:
        reply: dict[str, object] = {}
        assert _extract_reply_text(reply) == ""


class TestExtractSemanticText:
    def test_strips_self_mention(self) -> None:
        reply: dict[str, object] = {
            "content": {
                "elements": [
                    {"type": "person", "person": {"user_id": "bot"}},
                    {"type": "text_run", "text_run": {"text": " what is this?"}},
                ]
            }
        }
        result = _extract_semantic_text(reply, self_open_id="bot")
        assert "bot" not in result
        assert "what is this?" in result

    def test_keeps_other_mention(self) -> None:
        reply: dict[str, object] = {
            "content": {
                "elements": [
                    {"type": "person", "person": {"user_id": "user1"}},
                    {"type": "text_run", "text_run": {"text": " hi"}},
                ]
            }
        }
        result = _extract_semantic_text(reply, self_open_id="bot")
        assert "@user1" in result

    def test_string_content(self) -> None:
        reply: dict[str, object] = {"content": json.dumps({"elements": [{"type": "text_run", "text_run": {"text": "abc"}}]})}
        assert _extract_semantic_text(reply) == "abc"

    def test_invalid_json_string(self) -> None:
        reply: dict[str, object] = {"content": "raw text"}
        assert _extract_semantic_text(reply) == "raw text"

    def test_non_dict_content(self) -> None:
        assert _extract_semantic_text({"content": 123}) == ""

    def test_non_list_elements(self) -> None:
        assert _extract_semantic_text({"content": {"elements": "bad"}}) == ""

    def test_non_dict_element_skipped(self) -> None:
        assert _extract_semantic_text({"content": {"elements": [42]}}) == ""

    def test_person_non_dict(self) -> None:
        reply: dict[str, object] = {"content": {"elements": [{"type": "person", "person": "bad"}]}}
        assert _extract_semantic_text(reply) == "@"

    def test_docs_link(self) -> None:
        reply: dict[str, object] = {"content": {"elements": [{"type": "docs_link", "docs_link": {"url": "https://example.com"}}]}}
        assert "https://example.com" in _extract_semantic_text(reply)

    def test_docs_link_non_dict(self) -> None:
        reply: dict[str, object] = {"content": {"elements": [{"type": "docs_link", "docs_link": "bad"}]}}
        assert _extract_semantic_text(reply) == ""


class TestGetReplyUserId:
    def test_dict_user_id(self) -> None:
        assert _get_reply_user_id({"user_id": {"open_id": "oid1"}}) == "oid1"

    def test_dict_user_id_fallback(self) -> None:
        assert _get_reply_user_id({"user_id": {"user_id": "uid1"}}) == "uid1"

    def test_string_user_id(self) -> None:
        assert _get_reply_user_id({"user_id": "str_id"}) == "str_id"

    def test_missing_user_id(self) -> None:
        assert _get_reply_user_id({}) == ""


# ── Document link extraction coverage ─────────────────────────


class TestExtractDocsLinks:
    def test_extracts_feishu_links(self) -> None:
        replies: list[dict[str, object]] = [
            {
                "content": {
                    "elements": [
                        {"type": "docs_link", "docs_link": {"url": "https://feishu.cn/docx/abcdefghij1234567890"}},
                    ]
                }
            }
        ]
        links = _extract_docs_links(replies)
        assert len(links) == 1
        assert links[0]["doc_type"] == "docx"
        assert links[0]["token"] == "abcdefghij1234567890"

    def test_deduplicates(self) -> None:
        url = "https://feishu.cn/doc/abcdefghij1234567890"
        replies: list[dict[str, object]] = [
            {"content": {"elements": [{"type": "docs_link", "docs_link": {"url": url}}]}},
            {"content": {"elements": [{"type": "docs_link", "docs_link": {"url": url}}]}},
        ]
        assert len(_extract_docs_links(replies)) == 1

    def test_ignores_non_feishu_urls(self) -> None:
        replies: list[dict[str, object]] = [
            {"content": {"elements": [{"type": "docs_link", "docs_link": {"url": "https://google.com/doc/abc"}}]}}
        ]
        assert len(_extract_docs_links(replies)) == 0

    def test_string_content(self) -> None:
        replies: list[dict[str, object]] = [
            {
                "content": json.dumps(
                    {
                        "elements": [
                            {"type": "docs_link", "docs_link": {"url": "https://larkoffice.com/wiki/abcdefghij1234567890"}},
                        ]
                    }
                )
            }
        ]
        links = _extract_docs_links(replies)
        assert len(links) == 1

    def test_invalid_json_content(self) -> None:
        replies: list[dict[str, object]] = [{"content": "bad json {"}]
        assert len(_extract_docs_links(replies)) == 0

    def test_non_dict_content(self) -> None:
        replies: list[dict[str, object]] = [{"content": 42}]
        assert len(_extract_docs_links(replies)) == 0

    def test_non_list_elements(self) -> None:
        replies: list[dict[str, object]] = [{"content": {"elements": "bad"}}]
        assert len(_extract_docs_links(replies)) == 0

    def test_non_dict_element(self) -> None:
        replies: list[dict[str, object]] = [{"content": {"elements": [42]}}]
        assert len(_extract_docs_links(replies)) == 0

    def test_non_docs_link_type(self) -> None:
        replies: list[dict[str, object]] = [{"content": {"elements": [{"type": "text_run"}]}}]
        assert len(_extract_docs_links(replies)) == 0

    def test_link_data_non_dict(self) -> None:
        replies: list[dict[str, object]] = [{"content": {"elements": [{"type": "docs_link", "docs_link": 42}]}}]
        assert len(_extract_docs_links(replies)) == 0

    def test_empty_url(self) -> None:
        replies: list[dict[str, object]] = [{"content": {"elements": [{"type": "docs_link", "docs_link": {"url": ""}}]}}]
        assert len(_extract_docs_links(replies)) == 0

    def test_link_type_also_works(self) -> None:
        replies: list[dict[str, object]] = [
            {
                "content": {
                    "elements": [
                        {"type": "link", "link": {"url": "https://feishu.cn/sheet/abcdefghij1234567890"}},
                    ]
                }
            }
        ]
        links = _extract_docs_links(replies)
        assert len(links) == 1
        assert links[0]["doc_type"] == "sheet"


class TestResolveWikiLinks:
    @pytest.mark.asyncio
    async def test_resolves_wiki_links(self) -> None:
        client = AsyncMock(spec=FeishuClient)
        client.get_wiki_node.return_value = "resolved_token_123"
        links = [{"doc_type": "wiki", "token": "wiki_tok", "url": "https://feishu.cn/wiki/wiki_tok123456789"}]
        result = await _resolve_wiki_links(client, links)
        assert result[0]["resolved_token"] == "resolved_token_123"

    @pytest.mark.asyncio
    async def test_skips_non_wiki(self) -> None:
        client = AsyncMock(spec=FeishuClient)
        links = [{"doc_type": "docx", "token": "tok", "url": "https://feishu.cn/docx/tok"}]
        result = await _resolve_wiki_links(client, links)
        assert "resolved_token" not in result[0]
        client.get_wiki_node.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_failed_resolve(self) -> None:
        client = AsyncMock(spec=FeishuClient)
        client.get_wiki_node.return_value = None
        links = [{"doc_type": "wiki", "token": "tok", "url": "https://feishu.cn/wiki/tok"}]
        result = await _resolve_wiki_links(client, links)
        assert "resolved_token" not in result[0]


class TestFormatReferencedDocs:
    def test_empty_links(self) -> None:
        assert _format_referenced_docs([]) == ""

    def test_formats_links(self) -> None:
        links = [{"doc_type": "docx", "token": "tok1", "url": "https://feishu.cn/docx/tok1"}]
        result = _format_referenced_docs(links)
        assert "Referenced documents" in result
        assert "docx:tok1" in result

    def test_same_document_marker(self) -> None:
        links = [{"doc_type": "docx", "token": "current_tok", "url": "https://feishu.cn/docx/current_tok"}]
        result = _format_referenced_docs(links, current_file_token="current_tok")
        assert "same as current document" in result

    def test_resolved_token(self) -> None:
        links = [
            {"doc_type": "wiki", "token": "wiki_tok", "resolved_token": "real_tok", "url": "https://feishu.cn/wiki/wiki_tok"}
        ]
        result = _format_referenced_docs(links)
        assert "real_tok" in result


# ── Timeline selection coverage ────────────────────────────────


class TestTimelineSelection:
    def test_local_short_returns_all(self) -> None:
        timeline = [("u1", "t1", False)] * 5
        assert len(_select_local_timeline(timeline, 2)) == 5

    def test_local_long_centers_on_target(self) -> None:
        timeline = [("u1", f"t{i}", False) for i in range(30)]
        selected = _select_local_timeline(timeline, 15)
        assert len(selected) == 20
        assert timeline[15] in selected
        assert timeline[0] in selected
        assert timeline[29] in selected

    def test_whole_short_returns_all(self) -> None:
        timeline = [("u1", "t1", False)] * 5
        assert len(_select_whole_timeline(timeline, 2, 3)) == 5

    def test_whole_long_centers_on_current(self) -> None:
        timeline = [("u1", f"t{i}", False) for i in range(20)]
        selected = _select_whole_timeline(timeline, 10, 5)
        assert len(selected) == 12
        assert timeline[10] in selected
        assert timeline[5] in selected

    def test_whole_empty_selected_fallback(self) -> None:
        timeline = [("u1", f"t{i}", False) for i in range(20)]
        selected = _select_whole_timeline(timeline, -1, -1)
        assert len(selected) == 12


class TestTruncate:
    def test_short_text(self) -> None:
        assert _truncate("hello") == "hello"

    def test_long_text(self) -> None:
        result = _truncate("a" * 300)
        assert result.endswith("...")
        assert len(result) == 223

    def test_custom_limit(self) -> None:
        result = _truncate("a" * 100, 50)
        assert len(result) == 53
