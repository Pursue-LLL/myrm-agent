"""Generic HTTP webhook hosting provider.

[POS] HostingProvider that POSTs artifact bundles to user webhooks with SSRF guard.
"""

from __future__ import annotations

import io
import json
import logging
import zipfile

import httpx

from app.services.hosting.packager import PublishFile
from app.services.hosting.ssrf_guard import SSRFValidationError, validate_webhook_url
from app.services.hosting.types import HostingTarget, PublicationResult

logger = logging.getLogger(__name__)


class HttpWebhookProvider:
    provider_type = "http_webhook"

    async def test_connection(self, target: HostingTarget, credentials: dict[str, object]) -> tuple[bool, str]:
        webhook_url = target.config.get("webhook_url")
        if not webhook_url:
            return False, "webhook_url is required in target config."
        try:
            allow_http = target.config.get("allow_http", "").lower() == "true"
            validate_webhook_url(webhook_url, allow_http=allow_http)
        except SSRFValidationError as exc:
            return False, str(exc)
        return True, "Webhook URL validated."

    def _build_zip(self, files: dict[str, PublishFile]) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path, publish_file in files.items():
                if publish_file.encoding == "base64":
                    import base64

                    archive.writestr(path, base64.b64decode(publish_file.content))
                else:
                    archive.writestr(path, publish_file.content)
        return buffer.getvalue()

    async def publish(
        self,
        *,
        target: HostingTarget,
        credentials: dict[str, object],
        artifact_id: str,
        artifact_name: str,
        files: dict[str, PublishFile],
        existing_project_ref: str | None,
    ) -> PublicationResult:
        webhook_url = target.config.get("webhook_url")
        if not webhook_url:
            return PublicationResult(
                success=False,
                url="",
                publication_id="",
                project_ref="",
                status="ERROR",
                error="webhook_url is required.",
            )
        try:
            allow_http = target.config.get("allow_http", "").lower() == "true"
            safe_url = validate_webhook_url(webhook_url, allow_http=allow_http)
        except SSRFValidationError as exc:
            return PublicationResult(
                success=False,
                url="",
                publication_id="",
                project_ref="",
                status="ERROR",
                error=str(exc),
            )
        zip_bytes = self._build_zip(files)
        headers: dict[str, str] = {}
        auth_header = credentials.get("auth_header")
        auth_value = credentials.get("auth_value")
        if isinstance(auth_header, str) and isinstance(auth_value, str) and auth_header.strip():
            headers[auth_header.strip()] = auth_value
        data = {
            "artifact_id": artifact_id,
            "artifact_name": artifact_name,
            "project_ref": existing_project_ref or "",
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                safe_url,
                headers=headers,
                data=data,
                files={"artifact": ("artifact.zip", zip_bytes, "application/zip")},
                timeout=120.0,
            )
        if response.status_code >= 400:
            return PublicationResult(
                success=False,
                url="",
                publication_id="",
                project_ref=existing_project_ref or "",
                status="ERROR",
                error=f"Webhook returned {response.status_code}: {response.text[:300]}",
            )
        publication_id = ""
        url = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                publication_id = str(payload.get("publication_id") or payload.get("deployment_id") or "")
                url = str(payload.get("url") or payload.get("publication_url") or "")
        except json.JSONDecodeError:
            url = response.text.strip()[:512] if response.text else ""
        if not url:
            return PublicationResult(
                success=False,
                url="",
                publication_id=publication_id,
                project_ref=existing_project_ref or "",
                status="ERROR",
                error="Webhook response must include url field.",
            )
        return PublicationResult(
            success=True,
            url=url,
            publication_id=publication_id or artifact_id,
            project_ref=existing_project_ref or target.id,
            status="READY",
        )

    async def poll_status(
        self,
        *,
        target: HostingTarget,
        credentials: dict[str, object],
        publication_id: str,
    ) -> dict[str, str]:
        return {"id": publication_id, "status": "READY", "url": ""}
