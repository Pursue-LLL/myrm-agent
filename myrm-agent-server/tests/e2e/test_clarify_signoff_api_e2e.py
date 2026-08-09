"""M3 signoff clarify leg: SHPOIB API-only contract (R66 — no chrome bootstrap)."""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    cancel_e2e_chat_agent_via_api,
    create_e2e_chat_via_api,
    ensure_e2e_yolo_mode,
    get_e2e_api_url,
    resume_clarify_skip_via_api,
    start_clarify_turn_via_api,
    wait_e2e_provider_ready,
)
from dev_gate_contract import (  # noqa: E402
    SIGNOFF_CLARIFY_API_SEAL_CLARIFY,
    SIGNOFF_CLARIFY_API_SEAL_SKIP,
    clarify_skip_api_wait_sec,
    is_e2e_signoff_runtime,
)
from e2e_orchestrator import remaining_wall_sec, touch_wall_progress  # noqa: E402

from tests.api.agent.utils import get_lite_model_selection  # noqa: E402
from tests.support.e2e_runtime_guard import heartbeat_e2e_lease

E2E_PROMPT_SIGNOFF = (
    "CRITICAL: Your very first action MUST be a single ask_question_tool call — no text reply before it. "
    "You MUST call ask_question_tool exactly once before any other action. "
    'Use title "Pick stack". Ask one question with id "stack" and prompt '
    '"Which stack?" with two options: id "a" label "Option A", id "b" label "Option B". '
    "Set requires_confirmation to false. "
    "Do not use bash, write_file, render_ui_tool, or any other tools. "
    "If I skip without answering, reply with exactly: DONE-SKIPPED"
)


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
def test_clarify_signoff_api_contract_on_shpoib() -> None:
    """Signoff-only: clarification_required then Skip via agent-stream API on private backend."""
    if not is_e2e_signoff_runtime():
        pytest.skip("M3 signoff only (E2E_SIGNOFF=1)")
    if os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "").strip() != "1":
        pytest.fail(
            "signoff clarify requires pre-warmed SHPOIB pool (MYRM_E2E_SIGNOFF_CLARIFY_POOL=1)"
        )

    api_base = get_e2e_api_url()
    assert api_base, "E2E_API_BASE must be set by SHPOIB pool env"
    print(f"SIGNOFF_CLARIFY_API_BASE={api_base}", flush=True)

    if os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "").strip() == "1":
        provider_ready_timeout = 90.0
        if not wait_e2e_provider_ready(
            api_url=api_base, timeout_sec=provider_ready_timeout
        ):
            pytest.fail("provider not ready on signoff clarify pool backend")
    else:
        ensure_e2e_yolo_mode(api_url=api_base)
        if not wait_e2e_provider_ready(api_url=api_base, timeout_sec=30.0):
            pytest.fail("provider not ready within 30s on signoff clarify API leg")

    model_selection = get_lite_model_selection()
    api_timeout = min(
        float(clarify_skip_api_wait_sec()), max(15.0, remaining_wall_sec() - 30.0)
    )

    chat_id = ""
    clarify_result: dict[str, object] = {}
    for attempt in range(4):
        heartbeat_e2e_lease()
        touch_wall_progress()
        chat_id = f"signoff_clarify_{uuid.uuid4().hex[:8]}"
        create_e2e_chat_via_api(chat_id, api_url=api_base)
        clarify_result = start_clarify_turn_via_api(
            chat_id,
            query=E2E_PROMPT_SIGNOFF,
            model_selection=model_selection,
            api_url=api_base,
            timeout_sec=api_timeout,
        )
        if clarify_result.get("has_clarification"):
            break
        err = clarify_result.get("error")
        if isinstance(err, dict):
            error_type = str(err.get("error_type") or "")
            print(
                f"SIGNOFF_CLARIFY_ATTEMPT_FAIL attempt={attempt + 1}/4 "
                f"error_type={error_type!r} "
                f"event_types={clarify_result.get('event_types')!r}",
                flush=True,
            )
            if error_type == "AgentBusyError" and attempt + 1 < 4:
                cancel_e2e_chat_agent_via_api(chat_id, api_url=api_base)
                time.sleep(10.0)
            elif (
                error_type in ("AgentStreamClarifyIncomplete", "AgentStreamIdleTimeout")
                and attempt + 1 < 4
            ):
                cancel_e2e_chat_agent_via_api(chat_id, api_url=api_base)
                time.sleep(10.0 if error_type == "AgentStreamIdleTimeout" else 4.0)

    assert clarify_result.get("has_clarification"), (
        "Expected clarification_required on signoff clarify API leg; "
        f"event_types={clarify_result.get('event_types')!r} "
        f"error={clarify_result.get('error')!r}"
    )
    print(SIGNOFF_CLARIFY_API_SEAL_CLARIFY, flush=True)

    skip_result = resume_clarify_skip_via_api(
        chat_id,
        model_selection=model_selection,
        api_url=api_base,
        timeout_sec=min(api_timeout * 2.0, max(30.0, remaining_wall_sec() - 10.0)),
    )
    assert skip_result.get("ok"), (
        "Skip resume failed on signoff clarify API leg; "
        f"event_types={skip_result.get('event_types')!r} "
        f"final_text={skip_result.get('final_text')!r} "
        f"error={skip_result.get('error')!r}"
    )
    print(SIGNOFF_CLARIFY_API_SEAL_SKIP, flush=True)
