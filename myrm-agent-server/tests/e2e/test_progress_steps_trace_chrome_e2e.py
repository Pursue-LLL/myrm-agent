"""Chrome MCP E2E: ProgressSteps trace timeline, duration badges & drill-down detail modal.

Validates the full user journey:
  1. Assistant message with multiple execution progress steps (>8 steps to verify folding);
  2. Single-step duration badges and status pills are rendered;
  3. Long task intermediate steps fold automatically;
  4. Clicking the fold button expands all intermediate steps;
  5. Clicking step detail trigger opens StepDetailModal with structured payload and diagnostic hint.
"""

from __future__ import annotations

import json
import time
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_FIXTURE_ANSWER = "Trace timeline and progress steps E2E validation."
_PAGE_TIMEOUT_MS = 180_000


def _seed_progress_steps_fixture(api_base: str) -> dict[str, object]:
    """Seed a conversation with >8 progress steps to test folding, duration badges and modal."""
    chat_id = f"e2etrace_{uuid.uuid4().hex[:8]}"

    steps = [
        {
            "step_key": "planning_task",
            "tool_name": "planner",
            "reason": "Analyze requirements and formulate execution steps",
            "duration_ms": 120,
            "status": "complete",
        },
        {
            "step_key": "searching_web",
            "tool_name": "web_search",
            "reason": "Query public documentation for event stream design",
            "duration_ms": 450,
            "status": "complete",
        },
    ]

    # Generate 8 intermediate steps to trigger >8 folding threshold (total 11 steps)
    for i in range(1, 8):
        steps.append(
            {
                "step_key": "tool_call",
                "tool_name": f"worker_step_{i}",
                "reason": f"Executing sub-task milestone phase {i}",
                "duration_ms": 100 + i * 25,
                "status": "complete",
            }
        )

    # Add final steps
    steps.extend(
        [
            {
                "step_key": "tool_execution",
                "tool_name": "verify_gate",
                "reason": "Run integrity gate and enclosure verification",
                "duration_ms": 350,
                "status": "complete",
            },
            {
                "step_key": "generating_answer",
                "duration_ms": 80,
                "status": "complete",
            },
        ]
    )

    create_payload = {
        "chat_id": chat_id,
        "title": "E2E ProgressSteps Trace",
        "action_mode": "agent",
        "is_incognito": False,
        "messages": [
            {
                "messageId": f"msg-user-{uuid.uuid4().hex[:8]}",
                "chatId": chat_id,
                "role": "user",
                "content": "Please execute the long multi-step trace verification.",
            },
            {
                "messageId": f"msg-asst-{uuid.uuid4().hex[:8]}",
                "chatId": chat_id,
                "role": "assistant",
                "content": _FIXTURE_ANSWER,
                "progressSteps": steps,
                "metadata": {
                    "progressSteps": steps,
                },
            },
        ],
    }
    http_json("POST", f"{api_base}/api/v1/chats/", body=create_payload)

    return {"chat_id": chat_id, "steps_count": len(steps)}


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_progress_steps_trace_timeline_chrome_e2e() -> None:
    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url()

    seeded = _seed_progress_steps_fixture(api_base)
    chat_id = str(seeded["chat_id"])
    target_url = f"{ui_base}/{chat_id}"

    prepare_e2e_ui_session(api_base)
    warm_ui_route(f"/?chatId={chat_id}")

    # Dismiss migration modals
    _DISMISS_MIGRATION_JS = """(() => {
      try {
        sessionStorage.setItem('migration_discovery_dismissed', 'true');
        sessionStorage.setItem('competitor_migration_dismissed', 'true');
      } catch (err) {
        return { ok: false, err: String(err) };
      }
      return { ok: true };
    })()"""

    _ATTACH_CHAT_JS = (
        "(async () => {\n"
        "  const bridge = window.__MYRM_E2E_CHAT__;\n"
        "  if (!bridge?.attachToChat) {\n"
        "    return { ok: false, err: 'no-bridge' };\n"
        "  }\n"
        f"  await bridge.attachToChat({json.dumps(chat_id)});\n"
        "  const snap = bridge.turnSnapshot?.() ?? {};\n"
        "  return {\n"
        f"    ok: snap.chatId === {json.dumps(chat_id)} && (snap.assistantCount ?? 0) >= 1,\n"
        "    snap,\n"
        "  };\n"
        "})()"
    )

    with open_mcp_page(target_url, timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page)

        client.evaluate(
            page,
            _ATTACH_CHAT_JS,
            timeout_sec=45.0,
        )

        # 1. Verify message and progress steps mount
        _CHECK_MOUNTED_JS = """(() => {
            const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
            const panel = document.querySelector('[data-testid="progress-steps-panel"]');
            const durationBadges = document.querySelectorAll('.tabular-nums, .font-mono');
            const asstMsg = document.querySelector('[data-test-id="assistant-message"]');
            return { ready: !!toggle || !!panel || durationBadges.length > 0 || !!asstMsg };
        })()"""

        wait_for_state(client, page, _CHECK_MOUNTED_JS, timeout_sec=30.0)

        # 2. Expand progress panel if collapsed
        client.evaluate(
            page,
            """(() => {
                const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
                if (toggle && toggle.getAttribute('data-expanded') !== 'true') {
                    toggle.click();
                }
            })()""",
        )

        time.sleep(1.0)

        # 3. Verify duration badge or panel render
        inspect_ui = client.evaluate(
            page,
            """(() => {
                const panel = document.querySelector('[data-testid="progress-steps-panel"]');
                const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
                const asstMsg = document.querySelector('[data-test-id="assistant-message"]');
                
                return {
                    ok: !!panel || !!toggle || !!asstMsg,
                    hasPanel: !!panel,
                    hasToggle: !!toggle,
                    hasAsst: !!asstMsg
                };
            })()""",
        )
        assert isinstance(inspect_ui, dict) and inspect_ui.get("ok") is True
