"""Request recorder shared by every golden matrix: what reached the wire, with secrets and noise removed.

[INPUT]
- httpx (POS: patched ``send`` that every client library ends in)

[OUTPUT]
- Record / Case: one recorded request and one matrix cell (requests, result, error)
- record_request: a request reduced to method, URL, relevant headers and decoded body
- install_request_recorder: replaces ``httpx`` ``send`` so requests are recorded and answered by a fake provider

[POS]
Library-agnostic observation point. Only the final request on the wire is seen, so a baseline recorded from one
client library can be compared with the requests of another. Importing this module loads no client library.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx
import pytest

Record = dict[str, object]
Case = dict[str, object]

_SECRET_HEADERS = frozenset({"authorization", "x-api-key", "api-key", "x-goog-api-key"})
_KEPT_HEADER_PREFIXES = ("anthropic-", "x-", "api-", "openai-", "http-referer", "authorization", "content-type")
_IGNORED_HEADERS = frozenset({"content-type"})


def _multipart(content: bytes, content_type: str) -> dict[str, object]:
    """Fields of a multipart form; a file is reduced to its name, type, size and a short digest."""
    boundary = content_type.split("boundary=", 1)[1].strip('"').encode()
    fields: dict[str, object] = {}
    for part in content.split(b"--" + boundary):
        head, separator, data = part.partition(b"\r\n\r\n")
        name = re.search(rb'name="([^"]*)"', head)
        if not separator or name is None:
            continue
        data = data.removesuffix(b"\r\n")
        filename = re.search(rb'filename="([^"]*)"', head)
        kind = re.search(rb"(?i)content-type: *([^\r\n]+)", head)
        value: object = data.decode("utf-8", "replace")
        if filename is not None:
            value = {
                "filename": filename.group(1).decode(),
                "content_type": kind.group(1).decode() if kind else "",
                "size": len(data),
                "sha1": hashlib.sha1(data).hexdigest()[:10],
            }
        key = name.group(1).decode()
        if key in fields:
            previous = fields[key]
            fields[key] = [*previous, value] if isinstance(previous, list) else [previous, value]
        else:
            fields[key] = value
    return fields


def record_request(request: httpx.Request) -> Record:
    request.read()
    content_type = request.headers.get("content-type", "")
    try:
        if content_type.startswith("multipart/form-data"):
            body: object = _multipart(request.content, content_type)
        else:
            body = json.loads(request.content) if request.content else None
    except ValueError:
        body = {"__raw_len__": len(request.content or b"")}
    headers: dict[str, str] = {}
    for name, value in request.headers.items():
        key = name.lower()
        if key in _IGNORED_HEADERS or not key.startswith(_KEPT_HEADER_PREFIXES):
            continue
        headers[key] = f"<redacted:{value.split(' ')[0]}>" if key in _SECRET_HEADERS else value
    split = urlsplit(str(request.url))
    return {
        "method": request.method,
        "url": f"{split.scheme}://{split.netloc}{split.path}",
        "query": split.query,
        "headers": headers,
        "body": body,
    }


def install_request_recorder(
    monkeypatch: pytest.MonkeyPatch, answer: Callable[[httpx.Request], httpx.Response]
) -> list[Record]:
    """Replace ``httpx`` ``send`` so every request is recorded and answered with ``answer``'s provider response."""
    sink: list[Record] = []

    async def async_send(self: httpx.AsyncClient, request: httpx.Request, **kwargs: object) -> httpx.Response:
        sink.append(record_request(request))
        return answer(request)

    def sync_send(self: httpx.Client, request: httpx.Request, **kwargs: object) -> httpx.Response:
        sink.append(record_request(request))
        return answer(request)

    monkeypatch.setattr(httpx.AsyncClient, "send", async_send)
    monkeypatch.setattr(httpx.Client, "send", sync_send)
    return sink
