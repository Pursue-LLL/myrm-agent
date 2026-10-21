"""Feishu document, comment, wiki, card, and Bitable Mixin for FeishuClient.

[INPUT]
- (none — uses host class methods only)

[OUTPUT]
- FeishuDocumentsMixin: Mixin providing Drive, comment, wiki, CardKit, Bitable, and Docx operations.

[POS]
Mixin that adds document-level API methods to FeishuClient: Drive meta, comments,
wiki lookup, CardKit streaming, Bitable records, Docx blocks, and media download.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


class FeishuDocumentsMixin:
    """Drive, comment, wiki, CardKit, Bitable, and Docx operations.

    Requires the host class to provide:
    - ``ensure_token() -> str``
    - ``_get_http() -> httpx.AsyncClient``
    - ``_auth(token) -> dict``
    - ``_safe_json(resp, op) -> dict``
    - ``api_base: str``
    """

    api_base: str
    _MEDIA_TIMEOUT: float

    async def ensure_token(self) -> str: ...
    def _get_http(self) -> httpx.AsyncClient: ...
    def _auth(self, token: str) -> dict[str, str]: ...
    def _safe_json(self, resp: httpx.Response, operation: str) -> dict[str, object]: ...

    # ── Drive Meta ───────────────────────────────────────────────

    async def query_document_meta(
        self,
        file_token: str,
        file_type: str,
    ) -> dict[str, str]:
        """Fetch document title and URL via batch_query meta API."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.post(
            f"{self.api_base}/drive/v1/metas/batch_query",
            headers=self._auth(token),
            json={
                "request_docs": [{"doc_token": file_token, "doc_type": file_type}],
                "with_url": True,
            },
        )
        body = self._safe_json(resp, "query_document_meta")
        if body.get("code", -1) != 0:
            logger.warning("Feishu meta batch_query failed: %s", body.get("msg"))
            return {}

        metas = body.get("data", {})
        if not isinstance(metas, dict):
            return {}
        metas_list = metas.get("metas", [])
        if isinstance(metas_list, list) and metas_list:
            meta = metas_list[0] if isinstance(metas_list[0], dict) else {}
        elif isinstance(metas_list, dict):
            meta = metas_list.get(file_token, {})
            if not isinstance(meta, dict):
                meta = {}
        else:
            return {}
        return {
            "title": str(meta.get("title", "")),
            "url": str(meta.get("url", "")),
            "doc_type": str(meta.get("doc_type", file_type)),
        }

    # ── Comments ─────────────────────────────────────────────────

    async def batch_query_comment(
        self,
        file_token: str,
        file_type: str,
        comment_id: str,
        *,
        max_retries: int = 6,
        retry_delay: float = 1.0,
    ) -> dict[str, object]:
        """Fetch comment details via batch_query comment API.

        Retries up to *max_retries* times to handle Feishu's eventual consistency.
        """
        token = await self.ensure_token()
        http = self._get_http()

        for attempt in range(max_retries):
            resp = await http.post(
                f"{self.api_base}/drive/v1/files/{file_token}/comments/batch_query?file_type={file_type}&user_id_type=open_id",
                headers=self._auth(token),
                json={"comment_ids": [comment_id]},
            )
            body = self._safe_json(resp, "batch_query_comment")
            if body.get("code", -1) == 0:
                data = body.get("data", {})
                items = data.get("items", []) if isinstance(data, dict) else []
                if isinstance(items, list) and items:
                    item = items[0]
                    return item if isinstance(item, dict) else {}
                return {}
            if attempt < max_retries - 1:
                logger.info(
                    "Feishu batch_query_comment retry %d/%d: code=%s",
                    attempt + 1,
                    max_retries,
                    body.get("code"),
                )
                await asyncio.sleep(retry_delay)

        logger.warning("Feishu batch_query_comment failed after %d attempts", max_retries)
        return {}

    async def list_comments(
        self,
        file_token: str,
        file_type: str,
        *,
        is_whole: bool = False,
        max_pages: int = 5,
    ) -> list[dict[str, object]]:
        """List comments on a document (paginated)."""
        token = await self.ensure_token()
        http = self._get_http()
        all_items: list[dict[str, object]] = []
        page_token = ""

        for _ in range(max_pages):
            params = f"file_type={file_type}&is_whole={'true' if is_whole else 'false'}"
            params += "&page_size=100&user_id_type=open_id"
            if page_token:
                params += f"&page_token={page_token}"

            resp = await http.get(
                f"{self.api_base}/drive/v1/files/{file_token}/comments?{params}",
                headers=self._auth(token),
            )
            body = self._safe_json(resp, "list_comments")
            if body.get("code", -1) != 0:
                break
            data = body.get("data", {})
            if not isinstance(data, dict):
                break
            items = data.get("items", [])
            if isinstance(items, list):
                all_items.extend(i for i in items if isinstance(i, dict))
            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token", ""))
            if not page_token:
                break

        return all_items

    async def list_comment_replies(
        self,
        file_token: str,
        file_type: str,
        comment_id: str,
        *,
        expect_reply_id: str = "",
        max_retries: int = 6,
        retry_delay: float = 1.0,
        max_pages: int = 5,
    ) -> list[dict[str, object]]:
        """List all replies in a comment thread (paginated).

        If *expect_reply_id* is given and not found, retries for eventual consistency.
        """
        token = await self.ensure_token()
        http = self._get_http()

        for attempt in range(max_retries if expect_reply_id else 1):
            all_replies: list[dict[str, object]] = []
            page_token = ""
            fetch_ok = True

            for _ in range(max_pages):
                params = f"file_type={file_type}&page_size=100&user_id_type=open_id"
                if page_token:
                    params += f"&page_token={page_token}"

                resp = await http.get(
                    f"{self.api_base}/drive/v1/files/{file_token}/comments/{comment_id}/replies?{params}",
                    headers=self._auth(token),
                )
                body = self._safe_json(resp, "list_comment_replies")
                if body.get("code", -1) != 0:
                    fetch_ok = False
                    break
                data = body.get("data", {})
                if not isinstance(data, dict):
                    break
                items = data.get("items", [])
                if isinstance(items, list):
                    all_replies.extend(i for i in items if isinstance(i, dict))
                if not data.get("has_more"):
                    break
                page_token = str(data.get("page_token", ""))
                if not page_token:
                    break

            if not expect_reply_id or not fetch_ok:
                break
            if any(r.get("reply_id") == expect_reply_id for r in all_replies):
                break
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)

        return all_replies

    async def reply_to_comment(
        self,
        file_token: str,
        file_type: str,
        comment_id: str,
        text: str,
    ) -> tuple[bool, int]:
        """Post a reply to a local comment thread.

        Returns ``(success, api_code)``.
        """
        sanitized = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.post(
            f"{self.api_base}/drive/v1/files/{file_token}/comments/{comment_id}/replies?file_type={file_type}",
            headers=self._auth(token),
            json={
                "content": {
                    "elements": [
                        {"type": "text_run", "text_run": {"text": sanitized}},
                    ]
                }
            },
        )
        body = self._safe_json(resp, "reply_to_comment")
        code = int(body.get("code", -1))
        if code != 0:
            logger.warning("Feishu reply_to_comment failed: code=%s msg=%s", code, body.get("msg"))
        return code == 0, code

    async def add_whole_comment(
        self,
        file_token: str,
        file_type: str,
        text: str,
    ) -> bool:
        """Add a new whole-document comment."""
        sanitized = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.post(
            f"{self.api_base}/drive/v1/files/{file_token}/new_comments",
            headers=self._auth(token),
            json={
                "file_type": file_type,
                "reply_elements": [
                    {"type": "text", "text": sanitized},
                ],
            },
        )
        body = self._safe_json(resp, "add_whole_comment")
        if body.get("code", -1) != 0:
            logger.warning("Feishu add_whole_comment failed: %s", body.get("msg"))
            return False
        return True

    async def add_comment_reaction(
        self,
        file_token: str,
        file_type: str,
        reply_id: str,
        reaction_type: str = "OK",
    ) -> bool:
        """Add an emoji reaction to a document comment reply."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.post(
            f"{self.api_base}/drive/v2/files/{file_token}/comments/reaction?file_type={file_type}",
            headers=self._auth(token),
            json={
                "action": "add",
                "reply_id": reply_id,
                "reaction_type": reaction_type,
            },
        )
        body = self._safe_json(resp, "add_comment_reaction")
        return body.get("code", -1) == 0

    async def delete_comment_reaction(
        self,
        file_token: str,
        file_type: str,
        reply_id: str,
        reaction_type: str = "OK",
    ) -> bool:
        """Remove an emoji reaction from a document comment reply."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.post(
            f"{self.api_base}/drive/v2/files/{file_token}/comments/reaction?file_type={file_type}",
            headers=self._auth(token),
            json={
                "action": "delete",
                "reply_id": reply_id,
                "reaction_type": reaction_type,
            },
        )
        body = self._safe_json(resp, "delete_comment_reaction")
        return body.get("code", -1) == 0

    # ── Wiki ─────────────────────────────────────────────────────

    async def get_wiki_node(self, obj_token: str) -> str | None:
        """Reverse-lookup: find the wiki node_token for a document."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.get(
            f"{self.api_base}/wiki/v2/spaces/get_node?token={obj_token}",
            headers=self._auth(token),
        )
        body = self._safe_json(resp, "get_wiki_node")
        if body.get("code", -1) != 0:
            return None
        data = body.get("data", {})
        if not isinstance(data, dict):
            return None
        node = data.get("node", {})
        if isinstance(node, dict):
            wiki_token = node.get("node_token", "")
            return str(wiki_token) if wiki_token else None
        return None

    # ── CardKit Streaming API ────────────────────────────────────

    async def streaming_card_create(
        self,
        card_id: str,
        *,
        seq: int = 1,
    ) -> bool:
        """Initialize a CardKit streaming card session."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.post(
            f"{self.api_base}/cardkit/v1/cards/{card_id}/streaming/contents",
            headers=self._auth(token),
            json={"content": "", "seq": seq},
        )
        body = self._safe_json(resp, "streaming_create")
        if body.get("code", -1) != 0:
            logger.debug("CardKit streaming create failed: %s", body.get("msg"))
            return False
        return True

    async def streaming_card_update(
        self,
        card_id: str,
        content: str,
        *,
        seq: int,
        is_final: bool = False,
    ) -> bool:
        """Append or finalize streaming content for a CardKit card."""
        token = await self.ensure_token()
        http = self._get_http()
        payload: dict[str, object] = {
            "content": content,
            "seq": seq,
        }
        if is_final:
            payload["is_final"] = True
        resp = await http.patch(
            f"{self.api_base}/cardkit/v1/cards/{card_id}/streaming/contents",
            headers=self._auth(token),
            json=payload,
        )
        body = self._safe_json(resp, "streaming_update")
        if body.get("code", -1) != 0:
            logger.debug("CardKit streaming update failed: %s", body.get("msg"))
            return False
        return True

    # ── Bitable ──────────────────────────────────────────────────

    async def get_bitable_records(self, app_token: str, table_id: str) -> dict[str, object]:
        """Fetch records from a Feishu Bitable."""
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.get(
            f"{self.api_base}/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            headers=self._auth(token),
        )
        return self._safe_json(resp, "get_bitable_records")

    async def add_bitable_records(self, app_token: str, table_id: str, records: list[dict[str, object]]) -> bool:
        """Batch create records in a Feishu Bitable."""
        token = await self.ensure_token()
        http = self._get_http()
        payload = {"records": records}
        resp = await http.post(
            f"{self.api_base}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
            headers=self._auth(token),
            json=payload,
        )
        body = self._safe_json(resp, "add_bitable_records")
        if body.get("code", -1) != 0:
            logger.error("Failed to add bitable records: %s", body.get("msg"))
            return False
        return True

    async def create_bitable_app(self, name: str, folder_token: str = "") -> dict[str, str]:
        """Create a new Feishu Bitable App (Base).

        Returns dict with keys: app_token, url, default_table_id.
        """
        token = await self.ensure_token()
        http = self._get_http()
        payload: dict[str, object] = {"name": name}
        if folder_token:
            payload["folder_token"] = folder_token

        resp = await http.post(
            f"{self.api_base}/bitable/v1/apps",
            headers=self._auth(token),
            json=payload,
        )
        body = self._safe_json(resp, "create_bitable_app")
        if body.get("code", -1) != 0:
            logger.error("Failed to create bitable app: %s", body.get("msg"))
            return {}

        data = body.get("data", {})
        if not isinstance(data, dict):
            return {}
        app_obj = data.get("app", {})
        if not isinstance(app_obj, dict):
            return {}

        return {
            "app_token": str(app_obj.get("app_token", "")),
            "url": str(app_obj.get("url", "")),
            "default_table_id": str(app_obj.get("default_table_id", "")),
        }

    async def create_adaptive_bitable(
        self,
        name: str,
        rows: list[dict[str, object]],
        *,
        folder_token: str = "",
    ) -> dict[str, str]:
        """Create a Bitable App and automatically populate records from row dictionaries.

        Returns dict with app_token, table_id, and url.
        """
        if not rows:
            return {}

        app_info = await self.create_bitable_app(name, folder_token)
        app_token = app_info.get("app_token")
        if not app_token:
            return {}

        table_id = app_info.get("default_table_id")
        if not table_id:
            # Fetch default table ID from table list
            token = await self.ensure_token()
            http = self._get_http()
            resp = await http.get(
                f"{self.api_base}/bitable/v1/apps/{app_token}/tables",
                headers=self._auth(token),
            )
            tables_body = self._safe_json(resp, "list_bitable_tables")
            data = tables_body.get("data", {})
            if isinstance(data, dict):
                items = data.get("items", [])
                if isinstance(items, list) and items and isinstance(items[0], dict):
                    table_id = str(items[0].get("table_id", ""))

        if not table_id:
            return app_info

        # Format records for Feishu batch_create API
        records = [{"fields": row} for row in rows]
        success = await self.add_bitable_records(app_token, table_id, records)
        if not success:
            logger.warning("Created bitable app %s but failed to batch populate rows", app_token)

        return {
            "app_token": app_token,
            "table_id": table_id,
            "url": app_info.get("url", ""),
        }

    # ── Docx ─────────────────────────────────────────────────────

    async def download_media(self, file_token: str) -> bytes | None:
        """Download a document media file (image/attachment) by its token.

        Uses the tenant access token; returns None on any failure so callers
        can degrade gracefully (e.g. missing drive:drive scope → 403).
        """
        if not file_token.strip():
            return None
        token = await self.ensure_token()
        http = self._get_http()
        resp = await http.get(
            f"{self.api_base}/drive/v1/medias/{file_token}/download",
            headers=self._auth(token),
            timeout=self._MEDIA_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning(
                "Feishu media download failed for %s: HTTP %s",
                file_token,
                resp.status_code,
            )
            return None
        return resp.content

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

    async def list_drive_folder_files(
        self,
        folder_token: str,
        *,
        max_items: int = 20,
    ) -> list[dict[str, str]]:
        """List child files in a Feishu Drive folder (docx/doc only when filtered upstream)."""
        token = await self.ensure_token()
        http = self._get_http()
        all_items: list[dict[str, str]] = []
        page_token = ""
        page_size = min(max_items, 50)

        while len(all_items) < max_items:
            params: dict[str, str] = {
                "folder_token": folder_token,
                "page_size": str(page_size),
            }
            if page_token:
                params["page_token"] = page_token
            resp = await http.get(
                f"{self.api_base}/drive/v1/files",
                headers=self._auth(token),
                params=params,
            )
            body = self._safe_json(resp, "list_drive_folder_files")
            if body.get("code", -1) != 0:
                logger.warning("Feishu list_drive_folder_files failed: %s", body.get("msg"))
                break
            data = body.get("data", {})
            if not isinstance(data, dict):
                break
            raw_files = data.get("files", [])
            if isinstance(raw_files, list):
                for item in raw_files:
                    if not isinstance(item, dict):
                        continue
                    token_val = str(item.get("token", ""))
                    if not token_val:
                        continue
                    all_items.append(
                        {
                            "token": token_val,
                            "name": str(item.get("name", "untitled")),
                            "type": str(item.get("type", "")),
                        }
                    )
                    if len(all_items) >= max_items:
                        break
            if not data.get("has_more"):
                break
            page_token = str(data.get("next_page_token", "") or data.get("page_token", ""))
            if not page_token:
                break

        return all_items[:max_items]

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
