"""[INPUT]
- tests.support.minimal_app::build_minimal_app (POS: 轻量 FastAPI 测试应用)
- app.middleware.text_sanitizer_middleware::TextSanitizerMiddleware (POS: 请求文本净化，与线上一致)

[OUTPUT]
- text_api_client(): 挂载 files 路由 + 净化中间件的 httpx AsyncClient
- make_workspace(root): 含 LF / CRLF / BOM / 二进制 / 非 UTF-8 / 混合换行 / 超限 / 敏感文件的示例工作区
- read_text / save_text / copy_text: 对 GET / PUT / POST `/browse/text*` 的请求封装
- b64 / sha / reasons: 请求正文编码、内容版本令牌、错误详情 `{field: issue}`
- BASE / BOM: 端点路径与 UTF-8 BOM

[POS]
文本编辑 API 测试（`tests/api/files/test_workspace_text_{read,save,copy}.py`）共用的应用、工作区与请求辅助。
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from httpx import ASGITransport, AsyncClient, Response

from app.middleware.text_sanitizer_middleware import TextSanitizerMiddleware
from app.services.files.text_edit_io import EDITABLE_MAX_BYTES
from tests.support.minimal_app import build_minimal_app

BASE = "/api/v1/files/browse/text"
BOM = b"\xef\xbb\xbf"


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def error_body(resp: Response) -> dict:
    """The structured error, whether the handler wrapped it in ``detail`` or returned it at top level."""
    body = resp.json()
    return body["detail"] if "detail" in body else body


def reasons(resp: Response) -> dict[str, str]:
    """``{field: issue}`` from the response's error details."""
    error = error_body(resp).get("error") or {}
    return {d["field"]: d["issue"] for d in error.get("details", [])}


@asynccontextmanager
async def text_api_client() -> AsyncIterator[AsyncClient]:
    """The files routes behind the same request-text sanitiser the real server runs."""
    app = build_minimal_app(preset="files")
    app.add_middleware(TextSanitizerMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def make_workspace(root: Path) -> Path:
    """Fill ``root`` with one file of every kind the editor has to tell apart."""
    (root / "notes.txt").write_bytes(b"alpha\nbeta\n")
    (root / "windows.txt").write_bytes(b"alpha\r\nbeta\r\n")
    (root / "bom.txt").write_bytes(BOM + b"alpha\nbeta\n")
    (root / "data.bin").write_bytes(b"MZ\x00\x01")
    (root / "gbk.txt").write_bytes(b"\xd0\xd5\xc3\xfb\n")
    (root / "mixed.txt").write_bytes(b"a\r\nb\nc\r\n")
    (root / "big.txt").write_bytes(b"x" * (EDITABLE_MAX_BYTES + 100))
    (root / ".env").write_bytes(b"SECRET=1\n")
    (root / "src").mkdir()
    return root


async def read_text(client: AsyncClient, ws: Path, path: str) -> Response:
    return await client.get(BASE, params={"workspace": str(ws), "path": path})


async def save_text(client: AsyncClient, ws: Path, path: str, text: str, base_version: str) -> Response:
    return await client.put(
        BASE,
        json={"workspace": str(ws), "path": path, "content_b64": b64(text), "base_version": base_version},
    )


async def copy_text(client: AsyncClient, ws: Path, path: str, text: str) -> Response:
    return await client.post(f"{BASE}/copy", json={"workspace": str(ws), "path": path, "content_b64": b64(text)})
