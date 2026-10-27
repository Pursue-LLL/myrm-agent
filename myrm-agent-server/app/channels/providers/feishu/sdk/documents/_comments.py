"""Feishu document comment operations for FeishuClient.

[INPUT]
- ._host::FeishuHost (POS: members the host client supplies to the mixins)

[OUTPUT]
- FeishuCommentsMixin: comment queries, replies, whole-document comments, reactions.

[POS]
Comment-domain API methods of FeishuClient, used by the comment-event pipeline to read a thread and answer it.
"""

from __future__ import annotations

import asyncio
import logging

from ._host import FeishuHost

logger = logging.getLogger(__name__)


class FeishuCommentsMixin(FeishuHost):
    """Comment threads: read, reply, whole-document comment, reactions."""

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
        raw_code = body.get("code", -1)
        code = int(raw_code) if isinstance(raw_code, int | str) else -1
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
