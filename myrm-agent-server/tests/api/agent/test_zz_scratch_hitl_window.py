"""Scratch measurement (deleted after use): HITL approval -> immediate resume against the real agent-stream pipeline."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import build_approval_resume_value, get_model_selection
from tests.support.test_secrets import apply_test_secrets_to_environ

apply_test_secrets_to_environ(overwrite=True)

ROUNDS = int(os.environ.get("SCRATCH_ROUNDS", "4"))
PROMPT = (
    "Run exactly this command with the bash tool: curl -sS http://127.0.0.1:9/HOOKS_E2E_PROBE . "
    "After it finishes, whatever its result, reply with exactly: HOOKS-E2E-DONE"
)


def _events(client: TestClient, payload: dict[str, object], *, stop_on: str | None, on_stop=None):
    out: list[tuple[float, dict[str, object]]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload, timeout=240.0) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if not line or not line.strip().startswith("data: "):
                continue
            raw = line.strip()[6:]
            if raw == "[DONE]":
                break
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                now = time.monotonic()
                out.append((now, data))
                if stop_on and data.get("type") == stop_on and on_stop is not None:
                    on_stop(now)
                    on_stop = None
    return out


@pytest.mark.e2e
@pytest.mark.parametrize("round_no", list(range(ROUNDS)))
def test_scratch_resume_window(round_no: int, client: TestClient, mock_load_user_configs: pytest.AsyncMock) -> None:
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {"yoloModeEnabled": False, "autoModeEnabled": False}

    chat_id = f"scratch_{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/chats/", json={"chat_id": chat_id}).status_code == 200
    base: dict[str, object] = {"chatId": chat_id, "modelSelection": get_model_selection(), "actionMode": "agent", "enableMemory": False}

    resume_box: dict[str, object] = {}
    event_at: dict[str, float] = {}

    def _resume_worker() -> None:
        payload = {**base, "messageId": f"msg_{uuid.uuid4().hex[:8]}", "query": "", "resumeValue": build_approval_resume_value(allow_always=False)}
        attempts: list[tuple[float, str]] = []
        t_first = time.monotonic()
        for _attempt in range(40):
            evts = _events(client, payload, stop_on=None)
            kinds = [str(e.get("type")) + (":" + str(e.get("error_type")) if e.get("error_type") else "") for _, e in evts]
            attempts.append((time.monotonic() - t_first, ",".join(kinds[:3])))
            busy = any(e.get("error_type") == "AgentBusyError" for _, e in evts)
            if not busy:
                resume_box["events"] = evts
                break
            time.sleep(0.25)
            payload = {**payload, "messageId": f"msg_{uuid.uuid4().hex[:8]}"}
        resume_box["attempts"] = attempts

    holder: dict[str, threading.Thread] = {}

    def _on_event(now: float) -> None:
        event_at["t"] = now
        worker = threading.Thread(target=_resume_worker, daemon=True)
        holder["w"] = worker
        worker.start()

    first = _events(client, {**base, "messageId": f"msg_{uuid.uuid4().hex[:8]}", "query": PROMPT}, stop_on="tool_approval_request", on_stop=_on_event)
    t_end = time.monotonic()
    if "t" not in event_at:
        kinds = [str(e.get("type")) for _, e in first]
        pytest.skip(f"model did not request approval: {kinds[-8:]}")
    holder["w"].join(timeout=300)
    attempts = resume_box.get("attempts", [])
    resumed = resume_box.get("events", [])
    resumed_kinds = [str(e.get("type")) for _, e in resumed]
    text = "".join(str(e.get("data")) for _, e in resumed if e.get("type") == "message" and isinstance(e.get("data"), str))
    second_approvals = resumed_kinds.count("tool_approval_request")
    print(
        f"\nSCRATCH round={round_no} first_stream_tail_after_event={t_end - event_at['t']:.2f}s "
        f"resume_attempts={[(round(t, 2), k) for t, k in attempts]} second_approvals={second_approvals} "
        f"resumed_types={sorted(set(resumed_kinds))} final_text={text[-120:]!r}",
        flush=True,
    )
