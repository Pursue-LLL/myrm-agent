#!/usr/bin/env python3
"""Live integration: agent-stream render_ui → ui_update SSE → Chrome :3000 DOM.

Prerequisites:
- Backend :8080 healthy (`./myrm dev` or `python run.py`)
- Frontend :3000 running (`bun run dev` in myrm-agent-frontend)
- Chrome with CDP on :9222 (same as browser toolkit / MCP config)
- LITE_API_KEY or BASIC_API_KEY in .env.test / environment

Usage (from myrm-agent-server/):
  ../../scripts/dev/run-pytest-safe.sh .venv/bin/python scripts/dev/render_ui_chrome_verify.py
  ../../scripts/dev/run-pytest-safe.sh .venv/bin/python scripts/dev/render_ui_chrome_verify.py --skip-chrome
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import TypedDict

import httpx
from dotenv import load_dotenv

SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

load_dotenv(SERVER_ROOT / ".env.test")
load_dotenv(SERVER_ROOT / ".env")

from tests.api.agent.utils import get_lite_model_selection  # noqa: E402
from tests.support.test_secrets import load_test_secrets  # noqa: E402


class AgentStreamEvent(TypedDict, total=False):
    type: str
    subtype: str
    tool_name: str
    data: object


DEFAULT_BACKEND = "http://127.0.0.1:8080"
DEFAULT_FRONTEND = "http://localhost:3000"
DEFAULT_CDP = "http://127.0.0.1:9222"

RENDER_UI_QUERY = (
    'Call render_ui_tool exactly once. Required arguments: '
    'title="部署确认"; '
    'components=[{"id":"t1","type":"text","props":{"text":"确认重启 staging?"}}]; '
    'root_ids=["t1"]. '
    "Every component MUST include a type field. "
    "Do not use any other tools. After render_ui_tool succeeds, reply DONE."
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify render_ui SSE + Chrome interactive UI DOM.")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help="Backend base URL")
    parser.add_argument("--frontend", default=DEFAULT_FRONTEND, help="Frontend base URL")
    parser.add_argument("--cdp", default=DEFAULT_CDP, help="Chrome CDP endpoint")
    parser.add_argument("--skip-chrome", action="store_true", help="Only verify agent-stream SSE")
    parser.add_argument("--ui-timeout-ms", type=int, default=90_000, help="Chrome UI wait timeout")
    return parser.parse_args()


def _require_api_key() -> None:
    load_test_secrets()
    from tests.support.test_secrets import resolve_test_env

    if not (resolve_test_env("LITE_API_KEY") or resolve_test_env("BASIC_API_KEY")):
        raise SystemExit("Missing LITE_API_KEY or BASIC_API_KEY in .env.test / environment")


def _assert_backend_healthy(client: httpx.Client) -> None:
    response = client.get("/api/v1/health")
    if response.status_code != 200:
        raise SystemExit(f"Backend unhealthy: {response.status_code} {response.text[:200]}")


def _collect_agent_stream(client: httpx.Client, payload: dict[str, object]) -> list[AgentStreamEvent]:
    collected: list[AgentStreamEvent] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload, timeout=180.0) as response:
        if response.status_code != 200:
            raise SystemExit(f"agent-stream failed: {response.status_code} {response.text[:500]}")
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            raw = line[6:]
            if raw == "[DONE]":
                break
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                collected.append(data)  # type: ignore[arg-type]
    return collected


def _run_agent_stream(backend: str) -> tuple[str, list[AgentStreamEvent]]:
    chat_id = f"mcp_ui_{uuid.uuid4().hex[:8]}"
    message_id = f"msg_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "messageId": message_id,
        "chatId": chat_id,
        "query": RENDER_UI_QUERY,
        "modelSelection": get_lite_model_selection(),
        "actionMode": "agent",
        "enableMemory": False,
        "agentConfig": {"enabledBuiltinTools": ["render_ui"]},
    }

    with httpx.Client(base_url=backend, timeout=180.0) as client:
        create = client.post("/api/v1/chats/", json={"chat_id": chat_id})
        if create.status_code != 200:
            raise SystemExit(f"Create chat failed: {create.status_code} {create.text[:200]}")
        _assert_backend_healthy(client)
        events = _collect_agent_stream(client, payload)

    ui_events = [
        event
        for event in events
        if event.get("type") == "ui_update" and event.get("subtype") == "ui_artifact"
    ]
    render_steps = [
        event
        for event in events
        if event.get("type") == "tasks_steps" and event.get("tool_name") == "render_ui_tool"
    ]
    if not render_steps:
        raise SystemExit(f"No render_ui_tool tasks_steps; event_types={sorted({e.get('type') for e in events})}")
    if not ui_events:
        raise SystemExit(f"No ui_update SSE after render_ui; render_steps={len(render_steps)}")

    data = ui_events[0].get("data")
    if not isinstance(data, list) or not data:
        raise SystemExit("ui_update data is not a non-empty list")
    artifact = data[0]
    if not isinstance(artifact, dict) or artifact.get("title") != "部署确认":
        raise SystemExit(f"Unexpected ui artifact payload: {artifact!r}")

    print(f"SSE_OK chat_id={chat_id} ui_events={len(ui_events)} render_steps={len(render_steps)}")
    return chat_id, events


async def _verify_chrome_dom(
    *,
    frontend: str,
    chat_id: str,
    cdp_endpoint: str,
    ui_timeout_ms: int,
) -> None:
    from patchright.async_api import async_playwright

    page_url = f"{frontend.rstrip('/')}/{chat_id}"
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.connect_over_cdp(cdp_endpoint, timeout=15_000)
        except Exception as exc:
            raise SystemExit(f"CDP connect failed ({cdp_endpoint}): {exc}") from exc

        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()
        await page.goto(page_url, wait_until="domcontentloaded", timeout=30_000)
        selector = ".interactive-ui-container"
        try:
            await page.wait_for_selector(selector, timeout=ui_timeout_ms)
        except Exception:
            await page.reload(wait_until="domcontentloaded")
            await page.wait_for_selector(selector, timeout=ui_timeout_ms)

        container_count = await page.locator(selector).count()
        title_count = await page.get_by_text("部署确认").count()
        if container_count < 1 or title_count < 1:
            raise SystemExit(
                f"Chrome DOM check failed: containers={container_count} title_matches={title_count} url={page_url}"
            )
        print(f"CHROME_OK url={page_url} containers={container_count}")


def main() -> None:
    args = _parse_args()
    _require_api_key()
    chat_id, _ = _run_agent_stream(args.backend)
    if args.skip_chrome:
        print("SKIP_CHROME")
        return
    asyncio.run(
        _verify_chrome_dom(
            frontend=args.frontend,
            chat_id=chat_id,
            cdp_endpoint=args.cdp,
            ui_timeout_ms=args.ui_timeout_ms,
        )
    )
    print("LIVE_OK")


if __name__ == "__main__":
    main()
