"""Live E2E: a steer the server accepts mid-run is read by the real model; one sent after the run ended is refused.

REST only (no browser page): the turn streams over agent-stream while the steer arrives on the steer endpoint, so the
accepted-or-refused contract is exercised through the real server, the real executor and a real model.
"""

from __future__ import annotations

import json
import threading
import time
import uuid

import pytest
from cdp_chat.support import (
    fetch_chat_messages,
    nudge_agent_stream_turn,
    steer_chat_message,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import get_e2e_api_url, http_json, prepare_e2e_ui_session
from tests.support.e2e_provider_seed import seed_live_e2e_providers
from tests.support.e2e_runtime_guard import E2EResourceLedger

_LONG_TURN = "Count from 1 to 400, one number per line, then write COUNT_DONE."
_STEER_WINDOW_SEC = 60.0
_TURN_TIMEOUT_SEC = 240.0
_REGISTRY_CLEAR_SEC = 10.0


def _create_agent(api_url: str, suffix: str) -> str:
    created = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={"name": f"Steer Live {suffix}", "description": "Live E2E agent for steer delivery"},
    )
    assert isinstance(created, dict) and created.get("data", {}).get("id"), f"Create agent failed: {created}"
    return str(created["data"]["id"])


def _create_chat(api_url: str, chat_id: str, agent_id: str) -> None:
    created = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": f"Steer Live {chat_id}",
            "agent_id": agent_id,
            "action_mode": "agent",
            "messages": [],
        },
    )
    assert isinstance(created, dict) and created.get("success") is True, f"Create chat failed: {created}"


def _refusal_code(outcome: dict[str, object]) -> object:
    """The envelope code of a refused steer (404: no run is active for the chat)."""
    payload = outcome.get("payload")
    return payload.get("code") if isinstance(payload, dict) else None


def _assistant_text(api_url: str, chat_id: str) -> str:
    return "\n".join(
        json.dumps(message, ensure_ascii=False)
        for message in fetch_chat_messages(chat_id, api_url=api_url)
        if isinstance(message, dict) and message.get("role") == "assistant"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(420)
def test_steer_accepted_mid_run_reaches_the_model_and_a_late_one_is_refused(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider config not ready for the live steer E2E")

    suffix = uuid.uuid4().hex[:8]
    agent_id = _create_agent(api_url, suffix)
    e2e_resource_ledger.register("agent", agent_id)
    chat_id = f"e2esteer{suffix}"
    _create_chat(api_url, chat_id, agent_id)
    e2e_resource_ledger.register("chat", chat_id)

    codeword = f"PINEAPPLE{uuid.uuid4().int % 9000 + 1000}"
    turn: dict[str, object] = {}
    worker = threading.Thread(
        target=lambda: turn.update(
            nudge_agent_stream_turn(chat_id, agent_id, _LONG_TURN, api_url=api_url, timeout_sec=_TURN_TIMEOUT_SEC)
        ),
        daemon=True,
    )
    worker.start()

    # The steer endpoint refuses (envelope code 404) until the run registers, so the first acceptance is a mid-run steer.
    steer_message = f"Change of plan: stop counting now and answer with only the word {codeword}."
    started = time.monotonic()
    outcome: dict[str, object] = {}
    while time.monotonic() - started < _STEER_WINDOW_SEC:
        outcome = steer_chat_message(chat_id, steer_message, api_url=api_url)
        if outcome.get("ok") is True or not worker.is_alive():
            break
        time.sleep(1.0)
    print(f"E2E_STEER_LIVE: outcome={outcome} after={time.monotonic() - started:.1f}s turn_alive={worker.is_alive()}", flush=True)
    assert outcome.get("ok") is True, f"No steer was accepted while the turn ran: {outcome}; turn={turn}"

    worker.join(timeout=_TURN_TIMEOUT_SEC)
    assert not worker.is_alive(), "The streamed turn did not finish"
    assert turn.get("ok") is True, f"The streamed turn failed: {turn}"
    assert codeword in _assistant_text(api_url, chat_id), "A steer the run accepted must be read by the model"

    # The run's steering token is closed once the turn ends: a later steer is refused, not parked.
    cleared_by = time.monotonic() + _REGISTRY_CLEAR_SEC
    late = steer_chat_message(chat_id, "A steer after the run has ended", api_url=api_url)
    while late.get("ok") is True and time.monotonic() < cleared_by:
        time.sleep(1.0)
        late = steer_chat_message(chat_id, "A steer after the run has ended", api_url=api_url)
    assert late.get("ok") is False and _refusal_code(late) == 404, f"A steer after the run ended must be refused: {late}"
