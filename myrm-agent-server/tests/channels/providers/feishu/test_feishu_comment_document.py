"""The body of the document a Feishu comment turn is about: read once per turn, and a failure never blocks the reply."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.providers.feishu import FeishuChannel, comment_document
from app.channels.providers.feishu.api import FeishuClient
from app.channels.providers.feishu.comment_document import read_comment_document
from app.channels.providers.feishu.comment_handler import CommentRouteInfo, encode_comment_chat_id
from app.channels.providers.feishu.sdk import DocumentContent
from app.channels.types import ContextDocument, ContextDocumentStatus, InboundMessage

_ROUTE = CommentRouteInfo(file_type="docx", file_token="doxcnABC", comment_id="c1", is_whole=False)


def _client(outcome: DocumentContent | Exception) -> AsyncMock:
    client = AsyncMock(spec=FeishuClient)
    if isinstance(outcome, Exception):
        client.get_document_content.side_effect = outcome
    else:
        client.get_document_content.return_value = outcome
    return client


async def test_a_docx_body_is_read_as_markdown() -> None:
    client = _client(DocumentContent(code=0, markdown="# Plan\nship it"))

    document = await read_comment_document(client, _ROUTE)

    assert document == ContextDocument.ready("# Plan\nship it")
    client.get_document_content.assert_awaited_once_with("doxcnABC", "docx")


@pytest.mark.parametrize("file_type", ["doc", "sheet", "slides", "bitable", "mindnote", "file"])
async def test_a_file_without_a_markdown_export_is_not_read(file_type: str) -> None:
    client = _client(DocumentContent(code=0, markdown="never read"))
    route = CommentRouteInfo(file_type=file_type, file_token="tok", comment_id="c1", is_whole=True)

    assert await read_comment_document(client, route) == ContextDocument(ContextDocumentStatus.UNSUPPORTED)
    client.get_document_content.assert_not_awaited()


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (2889902, ContextDocumentStatus.DENIED),
        (99991672, ContextDocumentStatus.DENIED),
        (403, ContextDocumentStatus.DENIED),
        (2889925, ContextDocumentStatus.TOO_LARGE),
        (2889906, ContextDocumentStatus.UNAVAILABLE),
        (2889914, ContextDocumentStatus.UNAVAILABLE),
        (2889980, ContextDocumentStatus.UNAVAILABLE),
        (99991400, ContextDocumentStatus.UNAVAILABLE),
        (500, ContextDocumentStatus.UNAVAILABLE),
        (-1, ContextDocumentStatus.UNAVAILABLE),
    ],
)
async def test_a_refused_read_maps_to_the_reason_the_model_is_told(code: int, status: ContextDocumentStatus) -> None:
    document = await read_comment_document(_client(DocumentContent(code=code, message="refused")), _ROUTE)

    assert document == ContextDocument(status)


@pytest.mark.parametrize("fault", [httpx.ConnectError("boom"), RuntimeError("bug")], ids=["network", "bug"])
async def test_a_failed_read_never_raises(fault: Exception) -> None:
    document = await read_comment_document(_client(fault), _ROUTE)

    assert document == ContextDocument(ContextDocumentStatus.UNAVAILABLE)


async def test_a_slow_document_is_given_up_on(monkeypatch: pytest.MonkeyPatch) -> None:
    async def never_answers(*_: object) -> DocumentContent:
        await asyncio.sleep(5)
        return DocumentContent(code=0, markdown="too late")

    monkeypatch.setattr(comment_document, "_READ_TIMEOUT_SECONDS", 0.01)
    client = AsyncMock(spec=FeishuClient)
    client.get_document_content.side_effect = never_answers

    assert await read_comment_document(client, _ROUTE) == ContextDocument(ContextDocumentStatus.UNAVAILABLE)


async def test_the_operator_log_says_why_but_never_carries_the_body(caplog: pytest.LogCaptureFixture) -> None:
    secret = "QUARTERLY-NUMBERS-DO-NOT-LOG"
    with caplog.at_level(logging.INFO, logger=comment_document.logger.name):
        await read_comment_document(_client(DocumentContent(code=0, markdown=secret)), _ROUTE)
        await read_comment_document(_client(DocumentContent(code=2889902, message="no permission")), _ROUTE)

    assert "code=2889902" in caplog.text
    assert "no permission" in caplog.text
    assert secret not in caplog.text


def _channel(client: AsyncMock) -> FeishuChannel:
    channel = FeishuChannel(app_id="test_app_id", app_secret="test_app_secret")
    channel._client = client
    return channel


def _inbound(chat_id: str | None) -> InboundMessage:
    return InboundMessage(channel="feishu", sender_id="ou_1", content="what does section 3 say?", chat_id=chat_id)


async def test_a_comment_turn_gets_the_body_of_its_document() -> None:
    client = _client(DocumentContent(code=0, markdown="# Doc"))
    msg = _inbound(encode_comment_chat_id("docx", "doxcnABC", "c1", False))

    assert await _channel(client).read_context_document(msg) == ContextDocument.ready("# Doc")
    client.get_document_content.assert_awaited_once_with("doxcnABC", "docx")


@pytest.mark.parametrize("chat_id", ["oc_group_chat", "ou_direct_chat", None])
async def test_a_chat_message_has_no_document_and_costs_no_api_call(chat_id: str | None) -> None:
    client = _client(DocumentContent(code=0, markdown="# Doc"))

    assert await _channel(client).read_context_document(_inbound(chat_id)) is None
    client.get_document_content.assert_not_awaited()
