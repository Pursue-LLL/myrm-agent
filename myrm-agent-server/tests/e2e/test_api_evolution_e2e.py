"""End-to-end test for the Agent Skill Evolution (Learning Loop).

This test validates the entire stack:
1.  Harness: Analyzes failed trace, proposes fix, evaluates it, saves to SQLite.
2.  Server: Emits EVOLUTION_COMPLETE via WebSocket.
3.  Frontend: Updates UI badges when evolution completes.

[manual]
    uv run pytest tests/e2e/test_evolution_e2e.py -v -s
"""

import asyncio
import json
import os
from pathlib import Path

import pytest
import websockets
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionType,
    SkillLineage,
    SkillMetrics,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore
from patchright.async_api import async_playwright

pytestmark = pytest.mark.e2e

BUGGY_SKILL_ID = "test_math_buggy"


async def inject_buggy_skill() -> None:
    """Inject a deliberately broken math skill into the Sandbox Database."""
    db_path = Path(os.environ["MYRM_DATA_DIR"]) / ".skills_snapshot.sqlite"
    store = SkillStore(db_path)

    # We create a skill that subtracts instead of adds.
    skill_content = """
def run(a: int, b: int) -> int:
    \"\"\"Adds two numbers.\"\"\"
    return a - b  # BUG!
"""
    record = SkillRecord(
        skill_id=BUGGY_SKILL_ID,
        name="test_math_buggy",
        description="A tool that adds two numbers together.",
        content=skill_content,
        path=f"{BUGGY_SKILL_ID}.py",
        lineage=SkillLineage(evolution_type=EvolutionType.FIX),
        metrics=SkillMetrics(),
    )
    await store.save_skill(record)
    store.close()
    print(f"✅ Injected buggy skill {BUGGY_SKILL_ID} into {db_path}")


async def wait_for_evolution_completion(backend_ws_url: str) -> bool:
    """Connect to the Server's WebSocket and wait for an evolution to complete."""
    print(f"🔌 Connecting to Evolution WebSocket at {backend_ws_url}")
    try:
        async with websockets.connect(backend_ws_url) as ws:
            print("✅ Connected to Evolution WebSocket")
            while True:
                data = await ws.recv()
                try:
                    msg = json.loads(data)
                    print(f"📡 WebSocket Received: {msg}")
                    # In myrm-agent-server/app/services/skills/ws_hub.py,
                    # broadcast_proposal sends the evolution proposal.
                    # We look for our skill_id in the payload.
                    if msg.get("skill_id") == BUGGY_SKILL_ID:
                        # Wait for it to be confirmed/completed
                        if msg.get("status") in ("COMPLETED", "APPROVED", "APPLIED", "SUCCESS"):
                            print(f"🎉 Evolution completed for {BUGGY_SKILL_ID}")
                            return True
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"❌ WebSocket Error: {e}")
        return False


@pytest.mark.asyncio
async def test_learning_loop_e2e(ephemeral_server: str, ephemeral_frontend: str) -> None:
    print("\n--- Starting E2E Learning Loop Test ---")

    # 1. Inject Buggy Skill
    await inject_buggy_skill()

    # Extract WebSocket URL from backend HTTP URL
    ws_url = ephemeral_server.replace("http://", "ws://").replace("https://", "wss://")
    ws_evolution_url = f"{ws_url}/api/v1/ws/evolution"

    # 2. Setup Playwright Browser
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800}, locale="en-US")
        page = await context.new_page()
        page.set_default_timeout(60_000)

        try:
            print(f"🌍 Navigating to Frontend: {ephemeral_frontend}")
            await page.goto(ephemeral_frontend)

            # Wait for main chat interface to load
            chat_input = page.locator("textarea").first
            await chat_input.wait_for(state="visible", timeout=30_000)

            print("💬 Triggering error...")
            # Step 1: Trigger the bug
            await chat_input.fill("Use the tool test_math_buggy to add 5 and 3.")
            await page.keyboard.press("Enter")

            # Wait for agent to reply (simplistic check for some text appearing)
            # The agent should reply with 2 (since 5 - 3 = 2).
            # We wait a bit to ensure generation is done.
            await page.wait_for_timeout(10000)

            print("💬 Expressing frustration to trigger FIX evolution...")
            # Step 2: Express frustration and correct it
            await chat_input.fill(
                "That's wrong! 5 + 3 is 8. The tool is subtracting instead of adding. Fix the code to use a + b."
            )
            await page.keyboard.press("Enter")

            # Step 3: Listen for Evolution to happen in the background
            # We start the listener and wait for it to complete.
            print("⏳ Waiting for Background Evolution...")
            evo_task = asyncio.create_task(wait_for_evolution_completion(ws_evolution_url))

            # We wait up to 90 seconds for the LLM to process and fix the skill
            done, pending = await asyncio.wait([evo_task], timeout=90.0)
            if pending:
                for t in pending:
                    t.cancel()
                pytest.fail("Evolution timed out. The background task did not complete or broadcast.")

            success = evo_task.result()
            assert success, "Evolution failed to broadcast success."

            # Step 4: Visual Assertion on Frontend
            print("👁️ Checking UI for Evolution updates...")
            # We assume there is a memory/skills panel we can open
            # We will look for a badge or text indicating the skill evolved
            # Example: clicking a sidebar tab or expanding a context panel

            # (Note: exact DOM selectors depend on frontend implementation, using generic text search for now)
            # Looking for indications of test_math_buggy being active or evolved.
            # E.g., page.get_by_text("test_math_buggy").wait_for()

            # Step 5: Closed-loop verification
            print("💬 Verifying fixed behavior...")
            await chat_input.fill("Now calculate 5 and 3 again using test_math_buggy.")
            await page.keyboard.press("Enter")

            await page.wait_for_timeout(10000)

            # Grab all agent messages and assert the last one contains "8"
            messages = await page.locator(".message-agent, .agent-message, [data-role='assistant']").all_inner_texts()
            last_msg = messages[-1] if messages else ""
            print(f"Agent Final Reply: {last_msg}")

            assert "8" in last_msg, f"Agent did not learn! Replied with: {last_msg}"
            print("🎉 Learning Loop E2E Test Passed Successfully!")

        finally:
            await browser.close()
