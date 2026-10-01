"""Real Chrome MCP E2E and HTTP lifecycle integration for Clean Session Transcript Import.

Covers:
  - Lane-A: Live HTTP lifecycle: POST /api/chats/import-transcript -> verify DB persistence, CoT stripping, token stats
  - Lane-B / Lane-C: Real Chrome WebUI: open sidebar import modal -> paste transcript -> submit -> verify compression stats -> resume chat
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import get_e2e_api_url  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)


def _api_request(
    path: str, method: str = "GET", data: dict[str, object] | None = None
) -> dict[str, object] | None:
    url = f"{get_e2e_api_url()}{path}"
    payload = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"} if payload else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)
            return result if isinstance(result, dict) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def _is_backend_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{get_e2e_api_url()}/api/v1/health", timeout=5) as resp:  # noqa: S310
            return resp.status == 200
    except Exception:
        return False


_SAMPLE_HERMES_TRANSCRIPT = (
    json.dumps({
        "role": "user",
        "content": "Debug token leak with API key sk-ant-api03-abcdef1234567890abcdef1234567890",
        "timestamp": "2026-10-01T08:00:00Z"
    })
    + "\n"
    + json.dumps({
        "role": "assistant",
        "content": "<thinking>Checking secrets scrubbing and token reduction</thinking>Found secret, scrubbing and continuing.",
        "tool_calls": [{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "bash",
                "arguments": "{\"command\": \"cat /var/log/app.log | head -n 100\"}"
            }
        }],
        "timestamp": "2026-10-01T08:00:05Z"
    })
    + "\n"
    + json.dumps({
        "role": "tool",
        "name": "bash",
        "content": "[log line 1]\n[log line 2]\n[log line 3]\n[log line 4]\n[log line 5]\n[log line 6]\n[log line 7]\n[log line 8]",
        "timestamp": "2026-10-01T08:00:06Z"
    })
    + "\n"
    + json.dumps({
        "role": "assistant",
        "content": "All logs inspected. Leak resolved safely.",
        "timestamp": "2026-10-01T08:00:10Z"
    })
)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_import_session_http_lifecycle_e2e() -> None:
    """Lane-A: Verifies live HTTP import lifecycle, secret redaction, and database persistence."""
    if not _is_backend_ready():
        pytest.skip("Backend is not ready for live E2E")

    # 1. Post raw transcript
    import_resp = _api_request(
        "/api/v1/chats/import-transcript",
        method="POST",
        data={
            "raw_content": _SAMPLE_HERMES_TRANSCRIPT,
            "source_hint": "hermes",
        },
    )
    assert import_resp is not None, "API returned empty response"
    assert "chat_id" in import_resp, f"chat_id missing in {import_resp}"
    chat_id = str(import_resp["chat_id"])
    assert import_resp.get("turns_count") == 1
    assert import_resp.get("reduction_ratio", 0) > 0.3

    # 2. Verify messages persisted to SQLite without CoT
    messages_resp = _api_request(f"/api/v1/chats/{chat_id}/messages")
    assert messages_resp is not None, "Failed to retrieve messages"
    raw_data = messages_resp.get("data") if isinstance(messages_resp.get("data"), dict) else messages_resp
    messages = raw_data.get("messages", []) if isinstance(raw_data, dict) else []
    assert isinstance(messages, list) and len(messages) >= 2

    # User message check (secret redacted)
    user_msg = next((m for m in messages if m.get("role") == "user"), {})
    assert "sk-ant" not in str(user_msg.get("content", ""))
    assert "[REDACTED_" in str(user_msg.get("content", ""))

    # Assistant message check (thinking stripped)
    asst_msg = next((m for m in messages if m.get("role") == "assistant"), {})
    assert "<thinking>" not in str(asst_msg.get("content", ""))
    assert "All logs inspected" in str(asst_msg.get("content", ""))


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_import_session_webui_modal_and_resume_chrome_e2e() -> None:
    """Lane-B / Lane-C: Verifies WebUI sidebar import modal, paste mode, token compression display, and chat resumption."""
    if not _is_backend_ready():
        pytest.skip("Backend is not ready for live E2E")

    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)
    warm_ui_route("/")

    with open_mcp_page(f"{get_e2e_ui_url()}/") as (client, page):
        # 1 & 2. Open import modal and ensure paste tab textarea is ready
        modal_state = wait_for_state(
            client,
            page,
            """(() => {
                const modal = document.querySelector('[data-testid="session-import-modal"]');
                if (!modal) {
                    const btn = document.querySelector('[data-testid="import-session-btn"]');
                    if (btn) btn.click();
                    return { ready: false, step: "waiting_modal" };
                }
                const textarea = document.querySelector('[data-testid="import-paste-textarea"]');
                if (textarea) {
                    return { ready: true, step: "textarea_ready" };
                }
                const pasteTab = document.querySelector('[data-testid="import-tab-paste"]');
                if (pasteTab) {
                    pasteTab.click();
                }
                return { ready: false, step: "waiting_paste_tab" };
            })()""",
            timeout_sec=30.0,
        )
        assert modal_state.get("ready") is True, f"Modal did not become ready: {modal_state}"

        # 3. Enter transcript in paste mode and click Import
        payload_escaped = json.dumps(_SAMPLE_HERMES_TRANSCRIPT)
        input_eval = client.evaluate(
            page,
            f"""(() => {{
                const textarea = document.querySelector('[data-testid="import-paste-textarea"]');
                if (!textarea) return {{ ok: false, reason: 'textarea-missing' }};
                const proto = window.HTMLTextAreaElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                if (setter) {{
                    setter.call(textarea, {payload_escaped});
                }} else {{
                    textarea.value = {payload_escaped};
                }}
                textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));

                const submitBtn = document.querySelector('[data-testid="import-submit-btn"]');
                if (!submitBtn) return {{ ok: false, reason: 'submit-missing' }};
                if (submitBtn.disabled) return {{ ok: false, reason: 'submit-disabled' }};
                submitBtn.click();
                return {{ ok: true }};
            }})()""",
            timeout_sec=10.0,
        )
        assert isinstance(input_eval, dict) and input_eval.get("ok") is True, f"Submit failed: {input_eval}"

        # 4. Wait for import result stats banner to render
        result_state = wait_for_state(
            client,
            page,
            """(() => {
                const stats = document.querySelector('[data-testid="import-result-stats"]');
                const resumeBtn = document.querySelector('[data-testid="import-resume-btn"]');
                if (!stats || !resumeBtn) return { ready: false };
                const text = stats.textContent || '';
                return { ready: true, text };
            })()""",
            timeout_sec=30.0,
        )
        assert result_state.get("ready") is True, f"Result stats not rendered: {result_state}"
        stats_text = str(result_state.get("text", ""))
        assert "1" in stats_text  # 1 Turn
        assert "%" in stats_text  # Compression %

        # 5. Click resume button and verify URL navigation to /chat/
        nav_eval = client.evaluate(
            page,
            """(() => {
                const resumeBtn = document.querySelector('[data-testid="import-resume-btn"]');
                if (!resumeBtn) return { clicked: false };
                resumeBtn.click();
                return { clicked: true };
            })()""",
            timeout_sec=10.0,
        )
        assert isinstance(nav_eval, dict) and nav_eval.get("clicked") is True

        navigated = wait_for_state(
            client,
            page,
            """(() => {
                const path = window.location.pathname || '';
                return {
                    ready: path.startsWith('/chat_'),
                    pathname: path,
                };
            })()""",
            timeout_sec=30.0,
        )
        assert navigated.get("ready") is True, f"Did not navigate to chat: {navigated}"
        assert str(navigated.get("pathname", "")).startswith("/chat_")
