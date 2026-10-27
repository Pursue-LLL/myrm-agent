"""Tests for the Bitable operations of FeishuClient (documents/_bitable.py)."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from app.channels.providers.feishu.sdk import FeishuClient

from .support import mock_response

_BASE_URL = "https://x.feishu.cn/base/app_tok"
_APP = {"code": 0, "data": {"app": {"app_token": "app_tok", "url": _BASE_URL, "default_table_id": "tbl_001"}}}
_APP_WITHOUT_DEFAULT_TABLE = {"code": 0, "data": {"app": {"app_token": "app_tok", "url": "u", "default_table_id": ""}}}


class TestBitableRecords:
    @pytest.mark.asyncio
    async def test_get_records(self, client: FeishuClient) -> None:
        client._http.get = AsyncMock(return_value=mock_response(200, {"code": 0, "data": {"items": []}}))
        result = await client.get_bitable_records("app_tok", "tbl_001")
        assert result["code"] == 0
        assert client._http.get.await_args.args[0].endswith("/bitable/v1/apps/app_tok/tables/tbl_001/records")

    @pytest.mark.asyncio
    async def test_add_records_success(self, client: FeishuClient) -> None:
        client._http.post = AsyncMock(return_value=mock_response(200, {"code": 0}))
        assert await client.add_bitable_records("app_tok", "tbl_001", [{"fields": {}}]) is True
        assert client._http.post.await_args.args[0].endswith("/bitable/v1/apps/app_tok/tables/tbl_001/records/batch_create")
        assert client._http.post.await_args.kwargs["json"] == {"records": [{"fields": {}}]}

    @pytest.mark.asyncio
    async def test_add_records_failure(self, client: FeishuClient) -> None:
        client._http.post = AsyncMock(return_value=mock_response(200, {"code": 99, "msg": "fail"}))
        assert await client.add_bitable_records("app_tok", "tbl_001", [{"fields": {}}]) is False


class TestCreateBitableApp:
    @pytest.mark.asyncio
    async def test_returns_the_tokens_of_the_new_base(self, client: FeishuClient) -> None:
        client._http.post = AsyncMock(return_value=mock_response(200, _APP))
        assert await client.create_bitable_app("Tracker") == {
            "app_token": "app_tok",
            "url": _BASE_URL,
            "default_table_id": "tbl_001",
        }
        assert client._http.post.await_args.kwargs["json"] == {"name": "Tracker"}

    @pytest.mark.asyncio
    async def test_folder_is_sent_only_when_given(self, client: FeishuClient) -> None:
        client._http.post = AsyncMock(return_value=mock_response(200, _APP))
        await client.create_bitable_app("Tracker", "fld_1")
        assert client._http.post.await_args.kwargs["json"] == {"name": "Tracker", "folder_token": "fld_1"}

    @pytest.mark.asyncio
    async def test_a_refused_creation_is_empty(self, client: FeishuClient) -> None:
        client._http.post = AsyncMock(return_value=mock_response(200, {"code": 1254043, "msg": "no permission"}))
        assert await client.create_bitable_app("Tracker") == {}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("data", ["oops", {"app": "oops"}])
    async def test_a_malformed_body_is_empty(self, client: FeishuClient, data: object) -> None:
        client._http.post = AsyncMock(return_value=mock_response(200, {"code": 0, "data": data}))
        assert await client.create_bitable_app("Tracker") == {}


class TestCreateAdaptiveBitable:
    @pytest.mark.asyncio
    async def test_no_rows_creates_nothing(self, client: FeishuClient) -> None:
        client._http.post = AsyncMock()
        assert await client.create_adaptive_bitable("Tracker", []) == {}
        client._http.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rows_are_written_into_the_default_table(self, client: FeishuClient) -> None:
        client._http.post = AsyncMock(side_effect=[mock_response(200, _APP), mock_response(200, {"code": 0})])
        rows: list[dict[str, object]] = [{"name": "a"}, {"name": "b"}]

        result = await client.create_adaptive_bitable("Tracker", rows, folder_token="fld_1")

        assert result == {"app_token": "app_tok", "table_id": "tbl_001", "url": _BASE_URL}
        create_call, fill_call = client._http.post.await_args_list
        assert create_call.kwargs["json"] == {"name": "Tracker", "folder_token": "fld_1"}
        assert fill_call.args[0].endswith("/bitable/v1/apps/app_tok/tables/tbl_001/records/batch_create")
        assert fill_call.kwargs["json"] == {"records": [{"fields": {"name": "a"}}, {"fields": {"name": "b"}}]}

    @pytest.mark.asyncio
    async def test_a_refused_creation_writes_nothing(self, client: FeishuClient) -> None:
        client._http.post = AsyncMock(return_value=mock_response(200, {"code": 99, "msg": "fail"}))
        assert await client.create_adaptive_bitable("Tracker", [{"name": "a"}]) == {}
        assert client._http.post.await_count == 1

    @pytest.mark.asyncio
    async def test_a_missing_default_table_is_looked_up(self, client: FeishuClient) -> None:
        client._http.post = AsyncMock(
            side_effect=[mock_response(200, _APP_WITHOUT_DEFAULT_TABLE), mock_response(200, {"code": 0})]
        )
        client._http.get = AsyncMock(return_value=mock_response(200, {"code": 0, "data": {"items": [{"table_id": "tbl_9"}]}}))

        result = await client.create_adaptive_bitable("Tracker", [{"name": "a"}])

        assert result["table_id"] == "tbl_9"
        assert client._http.get.await_args.args[0].endswith("/bitable/v1/apps/app_tok/tables")
        assert client._http.post.await_args_list[1].args[0].endswith("/tables/tbl_9/records/batch_create")

    @pytest.mark.asyncio
    async def test_no_table_at_all_returns_the_base_without_rows(self, client: FeishuClient) -> None:
        client._http.post = AsyncMock(return_value=mock_response(200, _APP_WITHOUT_DEFAULT_TABLE))
        client._http.get = AsyncMock(return_value=mock_response(200, {"code": 0, "data": {"items": []}}))

        result = await client.create_adaptive_bitable("Tracker", [{"name": "a"}])

        assert result == {"app_token": "app_tok", "url": "u", "default_table_id": ""}
        assert client._http.post.await_count == 1

    @pytest.mark.asyncio
    async def test_failing_to_fill_the_rows_still_returns_the_base(
        self, client: FeishuClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        client._http.post = AsyncMock(side_effect=[mock_response(200, _APP), mock_response(200, {"code": 99, "msg": "fail"})])

        with caplog.at_level(logging.WARNING, logger="app.channels.providers.feishu.sdk.documents._bitable"):
            result = await client.create_adaptive_bitable("Tracker", [{"name": "a"}])

        assert result == {"app_token": "app_tok", "table_id": "tbl_001", "url": _BASE_URL}
        assert "failed to batch populate rows" in caplog.text
