"""Budget / i18n decoupling E2E — real server + browser verification."""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

import httpx
from patchright.async_api import async_playwright

from tests.api.agent.utils import get_model_selection
from tests.e2e_frontend.verifier_helpers import (
    BACKEND_BASE,
    FRONTEND_BASE,
    select_chat_model,
    submit_chat_message,
    sync_providers_from_env,
    verify_providers_ready_in_ui,
)

_BLOCK_POLICY = {
    "enabled": True,
    "daily_limit_usd": 0.01,
    "session_limit_usd": 0.01,
    "action_on_exceeded": "block",
}
_DISABLED_POLICY = {
    "enabled": False,
    "daily_limit_usd": 10.0,
    "session_limit_usd": 5.0,
    "action_on_exceeded": "finalize",
}


async def _set_budget_policy(client: httpx.AsyncClient, policy: dict[str, object]) -> None:
    response = await client.put("/api/v1/budget/policy", json=policy)
    response.raise_for_status()


async def _seed_today_spend(amount_usd: float) -> None:
    """Insert an assistant message with costUsd so budget guard can block."""
    from app.database.models.chat import Chat, Message
    from app.platform_utils import get_session_factory

    chat_id = f"budget-seed-{uuid.uuid4().hex[:10]}"
    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title="Budget E2E seed",
                action_mode="agent",
                source="e2e",
            )
        )
        db.add(
            Message(
                id=f"msg-{uuid.uuid4().hex[:8]}",
                chat_id=chat_id,
                role="assistant",
                content="budget seed",
                sent_at=datetime.now(timezone.utc),
                sent_timezone="UTC",
                extra_data={"costUsd": amount_usd},
            )
        )
        await db.commit()


async def _stream_agent_once(
    client: httpx.AsyncClient,
    *,
    chat_id: str,
    message_id: str,
    query: str,
) -> list[dict[str, object]]:
    request_data = {
        "messageId": message_id,
        "chatId": chat_id,
        "query": query,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    events: list[dict[str, object]] = []
    async with client.stream(
        "POST",
        "/api/v1/agents/agent-stream",
        json=request_data,
        timeout=180.0,
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                events.append(data)
    if not events:
        raise RuntimeError("agent-stream returned no SSE events")
    return events


async def _assert_progress_semantic_only() -> None:
    """Verify Server progress probe carries no UI copy (i18n decoupling)."""
    chat_id = f"progress-e2e-{uuid.uuid4().hex[:10]}"
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=180.0) as client:
        await _set_budget_policy(client, _DISABLED_POLICY)
        events = await _stream_agent_once(
            client,
            chat_id=chat_id,
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            query="Reply with exactly: PROGRESS_OK",
        )
        progress = [event for event in events if event.get("type") == "progress"]
        assert progress, "Expected stream lifecycle progress probe"
        payload = progress[0].get("data")
        assert isinstance(payload, dict)
        assert payload.get("status") == "started"
        assert payload.get("progress_pct") == 5
        assert "code" not in payload
        assert "message" not in payload
    print("Progress semantic-only E2E passed")


async def _assert_budget_policy_api() -> None:
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=30.0) as client:
        await _set_budget_policy(client, _BLOCK_POLICY)
        body = (await client.get("/api/v1/budget/status")).json()["data"]
        assert body["enabled"] is True

        await _set_budget_policy(client, _DISABLED_POLICY)
    print("Budget policy API E2E passed")


async def _assert_budget_blocked_sse_with_seeded_spend() -> None:
    """Real budget block via DB spend recovery — no mocked guard."""
    await _seed_today_spend(5.0)
    chat_id = f"budget-block-{uuid.uuid4().hex[:10]}"
    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=180.0) as client:
        await _set_budget_policy(client, _DISABLED_POLICY)
        await _set_budget_policy(client, _BLOCK_POLICY)
        events = await _stream_agent_once(
            client,
            chat_id=chat_id,
            message_id=f"msg-{uuid.uuid4().hex[:8]}",
            query="hello",
        )
        end_events = [event for event in events if event.get("type") == "message_end"]
        assert end_events, f"Expected message_end in budget-blocked stream; got types={[event.get('type') for event in events]}"
        assert end_events[-1].get("completion_status") == "budget_blocked"
        assert not any(event.get("type") == "progress" for event in events)
        await _set_budget_policy(client, _DISABLED_POLICY)
    print("Budget-blocked SSE E2E passed")


async def _assert_providers_visible_in_browser() -> None:
    """Verify frontend loads env-synced providers (real settings UI flow)."""
    await sync_providers_from_env()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            env={**os.environ},
        )
        page = await browser.new_page()
        try:
            await verify_providers_ready_in_ui(page)
        finally:
            await browser.close()
    print("Browser provider settings E2E passed")


async def _assert_budget_blocked_banner_in_browser() -> None:
    """Full user flow: seeded spend → block policy → UI shows frontend i18n banner."""
    await _seed_today_spend(5.0)
    await sync_providers_from_env()

    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=30.0) as client:
        await _set_budget_policy(client, _DISABLED_POLICY)
        await _set_budget_policy(client, _BLOCK_POLICY)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            env={**os.environ},
        )
        page = await browser.new_page()
        try:
            await page.goto(f"{FRONTEND_BASE}/", timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)
            await select_chat_model(page)
            await submit_chat_message(page, "hello")

            banner = page.get_by_text("budget", exact=False).or_(page.get_by_text("预算", exact=False))
            await banner.first.wait_for(state="visible", timeout=60000)
            print("Browser budget-blocked banner visible")
        finally:
            await browser.close()

    async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=30.0) as client:
        await _set_budget_policy(client, _DISABLED_POLICY)
    print("Browser budget-blocked banner E2E passed")


async def main() -> None:
    print("Starting budget/i18n E2E...", flush=True)
    try:
        await _assert_budget_policy_api()
        print("Step 1/5 budget API done", flush=True)
        await _assert_budget_blocked_sse_with_seeded_spend()
        print("Step 2/5 budget SSE done", flush=True)
        await _assert_progress_semantic_only()
        print("Step 3/5 progress semantic done", flush=True)
        await _assert_providers_visible_in_browser()
        print("Step 4/5 browser providers done", flush=True)
        await _assert_budget_blocked_banner_in_browser()
        print("Step 5/5 browser banner done", flush=True)
    finally:
        async with httpx.AsyncClient(base_url=BACKEND_BASE, timeout=30.0) as client:
            await _set_budget_policy(client, _DISABLED_POLICY)
    print("All budget/i18n E2E tests passed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"E2E FAILED: {exc}", file=sys.stderr)
        raise
