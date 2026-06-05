"""Vercel deployment client.

[INPUT]
- httpx (POS: Async HTTP client)
- tenacity (POS: Retry with exponential backoff)

[OUTPUT]
- VercelClient: deploy static files and poll deployment status

[POS]
Third-party hosting integration for artifact one-click deployment.
"""

import json
import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.services.deploy.deploy_packager import DeployFile

logger = logging.getLogger(__name__)


class VercelClient:
    """Client for Vercel REST API."""

    BASE_URL = "https://api.vercel.com"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True,
    )
    async def deploy(
        self,
        project_name: str,
        files: dict[str, DeployFile],
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Deploy files to Vercel."""
        # 1. 智能注入 vercel.json (处理 SPA 路由)
        if "index.html" in files and "vercel.json" not in files:
            logger.info("Injecting vercel.json for SPA routing in project %s", project_name)
            files["vercel.json"] = DeployFile(
                path="vercel.json",
                content=json.dumps(
                    {"rewrites": [{"source": "/(.*)", "destination": "/index.html"}]},
                    indent=2,
                ),
                encoding="utf-8",
            )

        # 2. 构造 Vercel API 要求的 files 数组
        vercel_files = []
        for file_path, deploy_file in files.items():
            entry: dict[str, str] = {"file": file_path, "data": deploy_file.content}
            if deploy_file.encoding == "base64":
                entry["encoding"] = "base64"
            vercel_files.append(entry)

        payload: dict[str, object] = {
            "name": project_name,
            "files": vercel_files,
            "projectSettings": {
                "framework": None  # 纯静态文件
            },
        }
        if project_id:
            payload["projectId"] = project_id

        # 3. 发起部署请求
        url = f"{self.BASE_URL}/v13/deployments"
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json=payload, timeout=60.0)

            if response.status_code >= 400:
                error_msg = response.text
                logger.error(f"Vercel deployment failed: {response.status_code} - {error_msg}")
                raise Exception(f"Vercel deployment failed: {error_msg}")

            # httpx response.json() is synchronous
            data = response.json()
            return {
                "deployment_id": data.get("id"),
                "url": f"https://{data.get('url')}",
                "project_id": data.get("projectId"),
                "status": data.get("readyState", "INITIALIZING"),
            }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True,
    )
    async def get_deployment_status(self, deployment_id: str) -> dict[str, Any]:
        """Get the status of a deployment."""
        url = f"{self.BASE_URL}/v13/deployments/{deployment_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, timeout=10.0)

            if response.status_code >= 400:
                raise Exception(f"Failed to get deployment status: {response.text}")

            # httpx response.json() is synchronous
            data = response.json()
            return {
                "id": data.get("id"),
                "url": f"https://{data.get('url')}",
                "status": data.get("readyState"),  # e.g., QUEUED, BUILDING, READY, ERROR
            }
