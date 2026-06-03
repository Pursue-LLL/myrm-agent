import json
import logging
from typing import Any, Dict

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

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
        reraise=True
    )
    async def deploy(self, project_name: str, files: Dict[str, str]) -> Dict[str, Any]:
        """
        Deploy files to Vercel.
        
        Args:
            project_name: The name of the project in Vercel.
            files: A dictionary mapping file paths to their string content.
                   e.g., {"index.html": "<h1>Hello</h1>", "style.css": "body { color: red; }"}
        """
        # 1. 智能注入 vercel.json (处理 SPA 路由)
        if "index.html" in files and "vercel.json" not in files:
            logger.info(f"Injecting vercel.json for SPA routing in project {project_name}")
            files["vercel.json"] = json.dumps({
                "rewrites": [
                    {"source": "/(.*)", "destination": "/index.html"}
                ]
            }, indent=2)

        # 2. 构造 Vercel API 要求的 files 数组
        vercel_files = []
        for file_path, content in files.items():
            vercel_files.append({
                "file": file_path,
                "data": content
            })

        payload = {
            "name": project_name,
            "files": vercel_files,
            "projectSettings": {
                "framework": None  # 纯静态文件
            }
        }

        # 3. 发起部署请求
        url = f"{self.BASE_URL}/v13/deployments"
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json=payload, timeout=60.0)
            
            if response.status_code >= 400:
                error_msg = response.text
                logger.error(f"Vercel deployment failed: {response.status_code} - {error_msg}")
                raise Exception(f"Vercel deployment failed: {error_msg}")
                
            data = response.json()
            return {
                "deployment_id": data.get("id"),
                "url": f"https://{data.get('url')}",
                "project_id": data.get("projectId"),
                "status": data.get("readyState", "INITIALIZING")
            }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
        reraise=True
    )
    async def get_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        """Get the status of a deployment."""
        url = f"{self.BASE_URL}/v13/deployments/{deployment_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, timeout=10.0)
            
            if response.status_code >= 400:
                raise Exception(f"Failed to get deployment status: {response.text}")
                
            data = response.json()
            return {
                "id": data.get("id"),
                "url": f"https://{data.get('url')}",
                "status": data.get("readyState") # e.g., QUEUED, BUILDING, READY, ERROR
            }
