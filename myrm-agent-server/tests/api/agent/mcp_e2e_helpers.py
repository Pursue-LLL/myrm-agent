"""Launch and preflight helpers for MCP Agent E2E tests."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import httpx

from tests.support.test_secrets import resolve_test_env

_MCP_12306_INDEX = Path(__file__).resolve().parents[4] / "12306-mcp" / "build" / "index.js"

_NPX_PATH = os.environ.get("NPX_PATH") or shutil.which("npx") or "npx"
_NODE_PATH = os.environ.get("NODE_PATH") or shutil.which("node") or "node"

TEST_WALL_CLOCK_LIMIT = 300
STREAM_TIMEOUT = 300
PREFLIGHT_TIMEOUT = 30
MAX_TOOL_STUCK_APPROVALS = 0

ENV_ERROR_KEYWORDS = (
    "Authentication",
    "Authorization",
    "Connection error",
    "InternalServerError",
    "Cannot connect",
    "Recursion limit",
    "Timeout",
    "timeout",
    "rate limit",
)


def resolve_12306_mcp_stdio() -> tuple[str, list[str], str, float]:
    """Resolve a fast stdio launch for Joooook/12306-mcp (avoid npx cold download)."""
    env_index = os.environ.get("MCP_12306_INDEX")
    if env_index and Path(env_index).is_file():
        return _NODE_PATH, [env_index], f"node {env_index}", 15.0

    if _MCP_12306_INDEX.is_file():
        return _NODE_PATH, [str(_MCP_12306_INDEX)], f"node {_MCP_12306_INDEX}", 15.0

    global_bin = shutil.which("12306-mcp")
    if global_bin:
        return global_bin, [], f"12306-mcp ({global_bin})", 15.0

    node = shutil.which("node")
    if node:
        candidate = Path(node).resolve().parent.parent / "lib/node_modules/12306-mcp/build/index.js"
        if candidate.is_file():
            return node, [str(candidate)], f"node {candidate}", 15.0

    npx_cmd = _NPX_PATH if Path(_NPX_PATH).exists() else shutil.which("npx")
    if npx_cmd:
        return npx_cmd, ["-y", "12306-mcp"], f"npx -y 12306-mcp ({npx_cmd})", 90.0

    raise RuntimeError("No Node 12306 MCP launcher found (install: npm install -g 12306-mcp)")


def preflight_llm_check() -> bool:
    """Send a trivial LLM request to verify connectivity before the real test."""
    api_key = resolve_test_env("BASIC_API_KEY")
    base_url = resolve_test_env("BASIC_BASE_URL")
    model_raw = resolve_test_env("BASIC_MODEL")
    if not all((api_key, base_url, model_raw)):
        return False

    model = model_raw.split("/", 1)[1] if "/" in model_raw else model_raw
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
        "stream": False,
    }
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=PREFLIGHT_TIMEOUT,
        )
        return resp.status_code == 200
    except (httpx.TimeoutException, httpx.ConnectError, OSError):
        return False


def prewarm_shared_venv() -> None:
    """Create shared venv before agent bash so E2E graph nodes are not spent on cold start."""
    from myrm_agent_harness.toolkits.code_execution.config import get_execution_config
    from myrm_agent_harness.toolkits.code_execution.executors.common.venv_manager import (
        VenvManager,
    )

    manager = VenvManager(get_execution_config())
    asyncio.run(manager.get_python_executable())
