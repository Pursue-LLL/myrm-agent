"""Cloudflare Pages direct-upload hosting provider.

[POS] HostingProvider implementation for Cloudflare Pages direct upload API.
"""

from __future__ import annotations

import io
import json
import logging
import zipfile

import httpx

from app.services.hosting.packager import PublishFile
from app.services.hosting.types import HostingTarget, PublicationResult

logger = logging.getLogger(__name__)


class CloudflarePagesProvider:
    provider_type = "cloudflare_pages"

    async def test_connection(self, target: HostingTarget, credentials: dict[str, object]) -> tuple[bool, str]:
        token = credentials.get("api_token")
        account_id = target.config.get("account_id")
        if not isinstance(token, str) or not token.strip():
            return False, "Cloudflare API token is required."
        if not account_id:
            return False, "Cloudflare account_id is required in target config."
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token.strip()}"}, timeout=20.0)
        if response.status_code >= 400:
            return False, f"Cloudflare API error: {response.text[:200]}"
        return True, "Cloudflare credentials valid."

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
        token = credentials.get("api_token")
        account_id = target.config.get("account_id")
        project_name = target.config.get("project_name") or artifact_name.lower().replace(" ", "-")[:50]
        if not isinstance(token, str) or not token.strip() or not account_id:
            return PublicationResult(
                success=False,
                url="",
                publication_id="",
                project_ref="",
                status="ERROR",
                error="Cloudflare api_token and account_id are required.",
            )
        zip_bytes = self._build_zip(files)
        headers = {"Authorization": f"Bearer {token.strip()}"}
        base = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects"
        async with httpx.AsyncClient(follow_redirects=False) as client:
            if not existing_project_ref:
                create_resp = await client.post(
                    base,
                    headers=headers,
                    json={"name": project_name, "production_branch": "main"},
                    timeout=30.0,
                )
                if create_resp.status_code >= 400:
                    return PublicationResult(
                        success=False,
                        url="",
                        publication_id="",
                        project_ref="",
                        status="ERROR",
                        error=f"Cloudflare project create failed: {create_resp.text[:300]}",
                    )
                project_ref = str(create_resp.json().get("result", {}).get("name", project_name))
            else:
                project_ref = existing_project_ref
            deploy_url = f"{base}/{project_ref}/deployments"
            response = await client.post(
                deploy_url,
                headers=headers,
                files={"file": ("artifact.zip", zip_bytes, "application/zip")},
                timeout=120.0,
            )
        if response.status_code >= 400:
            return PublicationResult(
                success=False,
                url="",
                publication_id="",
                project_ref=project_ref,
                status="ERROR",
                error=f"Cloudflare deploy failed: {response.text[:300]}",
            )
        payload = response.json().get("result", {})
        deployment_id = str(payload.get("id", ""))
        url = str(payload.get("url") or payload.get("aliases", [""])[0] if payload.get("aliases") else "")
        if url and not url.startswith("http"):
            url = f"https://{url}"
        return PublicationResult(
            success=True,
            url=url,
            publication_id=deployment_id,
            project_ref=project_ref,
            status=str(payload.get("latest_stage", {}).get("status", "READY")),
        )

    async def poll_status(
        self,
        *,
        target: HostingTarget,
        credentials: dict[str, object],
        publication_id: str,
        project_ref: str | None = None,
    ) -> dict[str, str]:
        token = credentials.get("api_token")
        account_id = target.config.get("account_id")
        project_name = project_ref or target.config.get("project_name")
        if not isinstance(token, str) or not token.strip() or not account_id or not project_name or not publication_id:
            return {"status": "ERROR", "error": "Missing Cloudflare poll context"}
        url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/"
            f"{project_name}/deployments/{publication_id}"
        )
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {token.strip()}"},
                timeout=20.0,
            )
        if response.status_code >= 400:
            return {"status": "ERROR", "error": response.text[:200]}
        payload = response.json().get("result", {})
        stage_status = str(payload.get("latest_stage", {}).get("status", "UNKNOWN"))
        normalized = stage_status
        if stage_status == "success":
            normalized = "READY"
        elif stage_status in {"failure", "canceled"}:
            normalized = "ERROR"
        deploy_url = str(payload.get("url") or "")
        if deploy_url and not deploy_url.startswith("http"):
            deploy_url = f"https://{deploy_url}"
        return {
            "id": publication_id,
            "status": normalized,
            "url": deploy_url,
        }
