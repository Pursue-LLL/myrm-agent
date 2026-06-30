"""Netlify static deploy hosting provider.

[POS] HostingProvider implementation for Netlify deploy hooks.
"""

from __future__ import annotations

import io
import logging
import zipfile

import httpx

from app.services.hosting.packager import PublishFile
from app.services.hosting.types import HostingTarget, PublicationResult

logger = logging.getLogger(__name__)


class NetlifyHostingProvider:
    provider_type = "netlify"

    async def test_connection(self, target: HostingTarget, credentials: dict[str, object]) -> tuple[bool, str]:
        token = credentials.get("access_token")
        if not isinstance(token, str) or not token.strip():
            return False, "Netlify access token is required."
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.netlify.com/api/v1/user",
                headers={"Authorization": f"Bearer {token.strip()}"},
                timeout=20.0,
            )
        if response.status_code >= 400:
            return False, f"Netlify API error: {response.text[:200]}"
        return True, "Netlify credentials valid."

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
        token = credentials.get("access_token")
        site_id = target.config.get("site_id") or existing_project_ref
        if not isinstance(token, str) or not token.strip() or not site_id:
            return PublicationResult(
                success=False,
                url="",
                publication_id="",
                project_ref="",
                status="ERROR",
                error="Netlify access_token and site_id are required.",
            )
        zip_bytes = self._build_zip(files)
        headers = {"Authorization": f"Bearer {token.strip()}"}
        url = f"https://api.netlify.com/api/v1/sites/{site_id}/deploys"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=headers,
                files={"file": ("artifact.zip", zip_bytes, "application/zip")},
                timeout=120.0,
            )
        if response.status_code >= 400:
            return PublicationResult(
                success=False,
                url="",
                publication_id="",
                project_ref=site_id,
                status="ERROR",
                error=f"Netlify deploy failed: {response.text[:300]}",
            )
        payload = response.json()
        deploy_id = str(payload.get("id", ""))
        deploy_url = str(payload.get("ssl_url") or payload.get("url") or "")
        return PublicationResult(
            success=True,
            url=deploy_url,
            publication_id=deploy_id,
            project_ref=site_id,
            status=str(payload.get("state", "READY")),
        )

    async def poll_status(
        self,
        *,
        target: HostingTarget,
        credentials: dict[str, object],
        publication_id: str,
    ) -> dict[str, str]:
        token = credentials.get("access_token")
        if not isinstance(token, str) or not token.strip():
            return {"status": "ERROR", "error": "Missing Netlify token"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.netlify.com/api/v1/deploys/{publication_id}",
                headers={"Authorization": f"Bearer {token.strip()}"},
                timeout=20.0,
            )
        if response.status_code >= 400:
            return {"status": "ERROR", "error": response.text[:200]}
        payload = response.json()
        return {
            "id": publication_id,
            "status": str(payload.get("state", "UNKNOWN")),
            "url": str(payload.get("ssl_url") or payload.get("url") or ""),
        }
