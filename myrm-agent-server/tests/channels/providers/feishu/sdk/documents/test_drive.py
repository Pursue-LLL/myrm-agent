"""Tests for the Drive and wiki lookups of FeishuClient (documents/_drive.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.channels.providers.feishu.sdk import FeishuClient

from .support import mock_response


class TestQueryDocumentMeta:
    @pytest.mark.asyncio
    async def test_success(self, client: FeishuClient) -> None:
        resp = mock_response(
            200,
            {
                "code": 0,
                "data": {"metas": [{"title": "My Doc", "url": "https://...", "doc_type": "docx"}]},
            },
        )
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta["title"] == "My Doc"

    @pytest.mark.asyncio
    async def test_failure(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 99, "msg": "not found"})
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta == {}

    @pytest.mark.asyncio
    async def test_data_not_dict(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0, "data": "not_a_dict"})
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta == {}

    @pytest.mark.asyncio
    async def test_metas_as_dict(self, client: FeishuClient) -> None:
        resp = mock_response(
            200,
            {
                "code": 0,
                "data": {
                    "metas": {
                        "tok_001": {
                            "title": "Dict Meta",
                            "url": "u",
                            "doc_type": "docx",
                        }
                    }
                },
            },
        )
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta["title"] == "Dict Meta"

    @pytest.mark.asyncio
    async def test_metas_dict_value_not_dict(self, client: FeishuClient) -> None:
        resp = mock_response(
            200,
            {
                "code": 0,
                "data": {"metas": {"tok_001": "bad_value"}},
            },
        )
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta == {"title": "", "url": "", "doc_type": "docx"}

    @pytest.mark.asyncio
    async def test_metas_empty_or_other(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0, "data": {"metas": 42}})
        client._http.post = AsyncMock(return_value=resp)
        meta = await client.query_document_meta("tok_001", "docx")
        assert meta == {}


class TestWiki:
    @pytest.mark.asyncio
    async def test_get_wiki_node(self, client: FeishuClient) -> None:
        resp = mock_response(
            200,
            {
                "code": 0,
                "data": {"node": {"node_token": "wiki_node_001"}},
            },
        )
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("obj_tok_001")
        assert token == "wiki_node_001"

    @pytest.mark.asyncio
    async def test_not_found(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 99, "msg": "not found"})
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("nonexist")
        assert token is None

    @pytest.mark.asyncio
    async def test_data_not_dict(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0, "data": "bad"})
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("obj")
        assert token is None

    @pytest.mark.asyncio
    async def test_empty_wiki_token(self, client: FeishuClient) -> None:
        resp = mock_response(
            200,
            {
                "code": 0,
                "data": {"node": {"node_token": ""}},
            },
        )
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("obj")
        assert token is None

    @pytest.mark.asyncio
    async def test_node_not_dict(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0, "data": {"node": "not_dict"}})
        client._http.get = AsyncMock(return_value=resp)
        token = await client.get_wiki_node("obj")
        assert token is None


class TestDownloadMedia:
    @pytest.mark.asyncio
    async def test_download_media_success(self, client: FeishuClient) -> None:
        resp = mock_response(200, {"code": 0})
        resp.content = b"\x89PNG\r\n\x1a\nfake-image"
        client._http.get = AsyncMock(return_value=resp)
        data = await client.download_media("img_v2_abc")
        assert data == b"\x89PNG\r\n\x1a\nfake-image"

    @pytest.mark.asyncio
    async def test_download_media_failure_returns_none(self, client: FeishuClient) -> None:
        resp = mock_response(403, {"code": 99991663, "msg": "no permission"})
        client._http.get = AsyncMock(return_value=resp)
        assert await client.download_media("img_v2_abc") is None
        assert await client.download_media("  ") is None


def _folder_page(files: list[object], *, has_more: bool = False, next_token: str = "") -> object:
    return mock_response(200, {"code": 0, "data": {"files": files, "has_more": has_more, "next_page_token": next_token}})


class TestListDriveFolderFiles:
    @pytest.mark.asyncio
    async def test_lists_the_files_of_a_folder_by_token_name_and_type(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(
            return_value=_folder_page([{"token": "t1", "name": "Spec", "type": "docx"}, {"token": "t2"}])
        )

        files = await client.list_drive_folder_files("fld_1")

        assert files == [
            {"token": "t1", "name": "Spec", "type": "docx"},
            {"token": "t2", "name": "untitled", "type": ""},
        ]
        assert client._http.get.call_args.kwargs["params"] == {"folder_token": "fld_1", "page_size": "20"}

    @pytest.mark.asyncio
    async def test_skips_entries_that_are_not_files_with_a_token(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(return_value=_folder_page(["junk", {"name": "no token"}, {"token": "t1", "name": "Keep"}]))

        files = await client.list_drive_folder_files("fld_1")

        assert [f["token"] for f in files] == ["t1"]

    @pytest.mark.asyncio
    async def test_follows_the_next_page_until_the_folder_is_exhausted(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(
            side_effect=[
                _folder_page([{"token": "t1"}], has_more=True, next_token="p2"),
                _folder_page([{"token": "t2"}]),
            ]
        )

        files = await client.list_drive_folder_files("fld_1")

        assert [f["token"] for f in files] == ["t1", "t2"]
        assert client._http.get.call_args_list[1].kwargs["params"]["page_token"] == "p2"

    @pytest.mark.asyncio
    async def test_stops_at_the_item_limit_without_asking_for_more(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(
            return_value=_folder_page([{"token": f"t{i}"} for i in range(5)], has_more=True, next_token="p2")
        )

        files = await client.list_drive_folder_files("fld_1", max_items=3)

        assert [f["token"] for f in files] == ["t0", "t1", "t2"]
        assert client._http.get.await_count == 1
        assert client._http.get.call_args.kwargs["params"]["page_size"] == "3"

    @pytest.mark.asyncio
    async def test_a_page_that_promises_more_without_a_token_ends_the_listing(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(return_value=_folder_page([{"token": "t1"}], has_more=True))

        files = await client.list_drive_folder_files("fld_1")

        assert [f["token"] for f in files] == ["t1"]
        assert client._http.get.await_count == 1

    @pytest.mark.asyncio
    async def test_keeps_what_was_listed_when_a_later_page_fails(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(
            side_effect=[
                _folder_page([{"token": "t1"}], has_more=True, next_token="p2"),
                mock_response(200, {"code": 99991672, "msg": "no permission"}),
            ]
        )

        files = await client.list_drive_folder_files("fld_1")

        assert [f["token"] for f in files] == ["t1"]

    @pytest.mark.asyncio
    async def test_a_folder_that_cannot_be_read_lists_nothing(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(return_value=mock_response(200, {"code": 1061002, "msg": "params error"}))

        assert await client.list_drive_folder_files("fld_1") == []

    @pytest.mark.asyncio
    async def test_a_reply_without_a_data_object_lists_nothing(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(return_value=mock_response(200, {"code": 0, "data": "oops"}))

        assert await client.list_drive_folder_files("fld_1") == []
