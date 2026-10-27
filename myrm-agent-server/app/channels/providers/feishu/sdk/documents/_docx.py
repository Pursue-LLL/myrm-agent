"""Feishu Docx content operations for FeishuClient.

[INPUT]
- ._host::FeishuHost (POS: members the host client supplies to the mixins)

[OUTPUT]
- DocumentContent: a document body as Markdown, or the reason it could not be read.
- FeishuDocxMixin: Docx block listing (wiki source sync), block append, and whole-document Markdown (comment context).

[POS]
Docx API methods of FeishuClient.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ._host import FeishuHost

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DocumentContent:
    """A document body as Markdown, or the reason it could not be read.

    ``code`` is 0 on success. Otherwise it is Feishu's error code from the response body, the HTTP status when
    the body carries none, and -1 when the reply was not a Feishu envelope at all.
    """

    code: int
    markdown: str = ""
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0


def _parse_content_response(resp: httpx.Response) -> DocumentContent:
    try:
        body = resp.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return DocumentContent(
            code=-1 if resp.is_success else resp.status_code,
            message=f"Unreadable response (HTTP {resp.status_code})",
        )
    raw_code = body.get("code")
    code = raw_code if isinstance(raw_code, int) and not isinstance(raw_code, bool) else -1
    message = str(body.get("msg") or f"HTTP {resp.status_code}")
    if not resp.is_success and code <= 0:
        # An HTTP failure is never a success, and a body without a Feishu code leaves only the status to report.
        return DocumentContent(code=resp.status_code, message=message)
    if code != 0:
        return DocumentContent(code=code, message=message)
    data = body.get("data")
    markdown = data.get("content") if isinstance(data, dict) else None
    if not isinstance(markdown, str):
        return DocumentContent(code=-1, message="Response carried no document content")
    return DocumentContent(code=0, markdown=markdown)


class FeishuDocxMixin(FeishuHost):
    """Docx content and blocks."""

    async def get_document_content(self, doc_token: str, doc_type: str = "docx") -> DocumentContent:
        """Fetch a whole document as Markdown in one call (``docs/v1/content``, scope ``docs:document.content:read``).

        Unlike ``get_docx_blocks`` the platform renders the tree, so tables and nested lists arrive intact.
        Feishu reports a failure with an HTTP error status and its own code in the body, so the body is read
        whatever the status.
        """
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.get(
            f"{self.api_base}/docs/v1/content",
            headers=self._auth(token),
            params={"doc_token": doc_token, "doc_type": doc_type, "content_type": "markdown"},
            timeout=self._MEDIA_TIMEOUT,
        )
        return _parse_content_response(resp)

    async def get_docx_blocks(self, document_id: str) -> dict[str, object]:
        """Get all blocks from a Feishu Docx document (paged until exhausted).

        Bounded by max_pages as a defensive guard against API loops returning
        a stale page_token while has_more stays true.
        """
        token = await self.ensure_token()
        http = self._get_http()
        all_items: list[object] = []
        page_token = ""
        page_size = 500
        max_pages = 200

        for _ in range(max_pages):
            params: dict[str, str] = {"page_size": str(page_size)}
            if page_token:
                params["page_token"] = page_token
            resp = await http.get(
                f"{self.api_base}/docx/v1/documents/{document_id}/blocks",
                headers=self._auth(token),
                params=params,
            )
            body = self._safe_json(resp, "get_docx_blocks")
            if body.get("code", -1) != 0:
                if not all_items:
                    return body
                logger.warning("Feishu get_docx_blocks page failed: %s", body.get("msg"))
                break
            data = body.get("data", {})
            if not isinstance(data, dict):
                break
            raw_items = data.get("items")
            if isinstance(raw_items, list):
                all_items.extend(raw_items)
            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token", ""))
            if not page_token:
                break

        return {"code": 0, "data": {"items": all_items}}

    async def append_docx_blocks(self, document_id: str, block_id: str, children: list[dict[str, object]]) -> bool:
        """Append blocks as children of a specific block in a Feishu Docx document."""
        token = await self.ensure_token()
        http = self._get_http()
        payload = {"children": children}
        resp = await http.post(
            f"{self.api_base}/docx/v1/documents/{document_id}/blocks/{block_id}/children/batch_create",
            headers=self._auth(token),
            json=payload,
        )
        body = self._safe_json(resp, "append_docx_blocks")
        if body.get("code", -1) != 0:
            logger.error("Failed to append docx blocks: %s", body.get("msg"))
            return False
        return True
