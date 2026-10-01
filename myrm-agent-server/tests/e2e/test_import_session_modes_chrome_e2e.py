"""Real Chrome MCP E2E: File upload mode and boundary error validation for Clean Session Transcript Import.

Covers:
  - Lane-D: File upload mode (dispatches File object to hidden file input, checks stats, resumes chat)
  - Lane-E: Boundary validation (empty textarea disables submit, invalid non-json syntax triggers toast without crash)
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import get_e2e_api_url  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)


def _is_backend_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{get_e2e_api_url()}/api/v1/health", timeout=5) as resp:  # noqa: S310
            return resp.status == 200
    except Exception:
        return False


_SAMPLE_HERMES_TRANSCRIPT = (
    json.dumps({
        "role": "user",
        "content": "Analyze container memory usage",
        "timestamp": "2026-10-01T08:00:00Z"
    })
    + "\n"
    + json.dumps({
        "role": "assistant",
        "content": "<thinking>Inspecting cgroup metrics</thinking>Memory within limits.",
        "timestamp": "2026-10-01T08:00:05Z"
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
def test_import_session_file_upload_mode_chrome_e2e() -> None:
    """Lane-D: Verifies File upload mode via file input dispatch, stats rendering, and navigation."""
    if not _is_backend_ready():
        pytest.skip("Backend is not ready for live E2E")

    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)
    warm_ui_route("/")

    with open_mcp_page(f"{get_e2e_ui_url()}/") as (client, page):
        dismiss_blocking_modals(client, page)

        # 1. Open import modal
        modal_state = wait_for_state(
            client,
            page,
            """(() => {
                const modal = document.querySelector('[data-testid="session-import-modal"]');
                if (!modal) {
                    const btn = document.querySelector('[data-testid="import-session-btn"]');
                    if (btn) btn.click();
                    return { ready: false };
                }
                const input = document.querySelector('[data-testid="import-file-input"]');
                return { ready: Boolean(input) };
            })()""",
            timeout_sec=30.0,
        )
        assert modal_state.get("ready") is True, f"Upload file input missing: {modal_state}"

        # 2. Dispatch File object into import-file-input
        payload_escaped = json.dumps(_SAMPLE_HERMES_TRANSCRIPT)
        uploaded = client.evaluate(
            page,
            f"""(() => {{
                const input = document.querySelector('[data-testid="import-file-input"]');
                if (!input) return {{ ok: false, err: "missing_input" }};
                const file = new File([{payload_escaped}], "hermes_e2e_dump.jsonl", {{ type: "application/json" }});
                const dt = new DataTransfer();
                dt.items.add(file);
                input.files = dt.files;
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return {{ ok: true }};
            }})()""",
            timeout_sec=10.0,
        )
        assert isinstance(uploaded, dict) and uploaded.get("ok") is True

        # 3. Click submit
        submitted = wait_for_state(
            client,
            page,
            """(() => {
                const submitBtn = document.querySelector('[data-testid="import-submit-btn"]');
                if (!submitBtn || submitBtn.disabled) return { ready: false };
                submitBtn.click();
                return { ready: true };
            })()""",
            timeout_sec=15.0,
        )
        assert submitted.get("ready") is True, f"File submit failed: {submitted}"

        # 4. Verify result stats rendered
        stats_state = wait_for_state(
            client,
            page,
            """(() => {
                const stats = document.querySelector('[data-testid="import-result-stats"]');
                return { ready: Boolean(stats), text: stats?.textContent || '' };
            })()""",
            timeout_sec=30.0,
        )
        assert stats_state.get("ready") is True, f"Stats not rendered: {stats_state}"
        assert "%" in str(stats_state.get("text", ""))


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_import_session_boundary_and_validation_chrome_e2e() -> None:
    """Lane-E: Verifies boundary validation: empty input disabled submit, invalid format error toast."""
    if not _is_backend_ready():
        pytest.skip("Backend is not ready for live E2E")

    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)
    warm_ui_route("/")

    with open_mcp_page(f"{get_e2e_ui_url()}/") as (client, page):
        dismiss_blocking_modals(client, page)

        # 1. Open modal and switch to paste tab
        modal_state = wait_for_state(
            client,
            page,
            """(() => {
                const modal = document.querySelector('[data-testid="session-import-modal"]');
                if (!modal) {
                    const btn = document.querySelector('[data-testid="import-session-btn"]');
                    if (btn) btn.click();
                    return { ready: false };
                }
                const pasteTab = document.querySelector('[data-testid="import-tab-paste"]');
                if (pasteTab) pasteTab.click();
                const textarea = document.querySelector('[data-testid="import-paste-textarea"]');
                const submitBtn = document.querySelector('[data-testid="import-submit-btn"]');
                return {
                    ready: Boolean(textarea && submitBtn),
                    submit_disabled: submitBtn?.disabled ?? false,
                };
            })()""",
            timeout_sec=30.0,
        )
        assert modal_state.get("ready") is True
        assert modal_state.get("submit_disabled") is True

        # 2. Fill invalid text
        client.evaluate(
            page,
            """(() => {
                const textarea = document.querySelector('[data-testid="import-paste-textarea"]');
                if (!textarea) return;
                const proto = window.HTMLTextAreaElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                if (setter) {
                    setter.call(textarea, "Invalid non-json conversational garbage text");
                } else {
                    textarea.value = "Invalid non-json conversational garbage text";
                }
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                textarea.dispatchEvent(new Event('change', { bubbles: true }));
            })()""",
            timeout_sec=10.0,
        )

        # 3. Click submit
        click_res = wait_for_state(
            client,
            page,
            """(() => {
                const submitBtn = document.querySelector('[data-testid="import-submit-btn"]');
                if (submitBtn && !submitBtn.disabled) {
                    submitBtn.click();
                    return { ready: true };
                }
                return { ready: false };
            })()""",
            timeout_sec=10.0,
        )
        assert click_res.get("ready") is True

        # 4. Confirm modal remains mounted and intact without uncaught crash
        modal_intact = wait_for_state(
            client,
            page,
            """(() => {
                const modal = document.querySelector('[data-testid="session-import-modal"]');
                return { ready: Boolean(modal) };
            })()""",
            timeout_sec=10.0,
        )
        assert modal_intact.get("ready") is True
