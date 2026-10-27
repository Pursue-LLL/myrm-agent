"""Feishu Drive and wiki lookups for FeishuClient.

[INPUT]
- ._host::FeishuHost (POS: members the host client supplies to the mixins)

[OUTPUT]
- FeishuDriveMixin: document meta, wiki node lookup, media download, Drive folder listing.

[POS]
Read-only Drive/wiki API methods of FeishuClient. The comment pipeline reads a document's title through
``query_document_meta``; the wiki source sync lists folders and downloads embedded media.
"""

from __future__ import annotations

import logging

from ._host import FeishuHost

logger = logging.getLogger(__name__)


class FeishuDriveMixin(FeishuHost):
    """Drive meta, wiki node lookup, media download and folder listing."""

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
