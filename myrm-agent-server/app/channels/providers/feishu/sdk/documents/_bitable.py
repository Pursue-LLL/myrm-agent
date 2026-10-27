"""Feishu Bitable operations for FeishuClient.

[INPUT]
- ._host::FeishuHost (POS: members the host client supplies to the mixins)

[OUTPUT]
- FeishuBitableMixin: Bitable record read and batch create, Base creation, Base creation with rows.

[POS]
Bitable API methods of FeishuClient.
"""

from __future__ import annotations

import logging

from ._host import FeishuHost

logger = logging.getLogger(__name__)


class FeishuBitableMixin(FeishuHost):
    """Bitable records and Bases."""

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
