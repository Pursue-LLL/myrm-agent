"""Chrome E2E: the expert export review shows redaction finding kinds in the user's language.

Real user flow on /settings/agents: open an agent that carries a token and a local path in its
system prompt, press "Export agent", and read the review panel. The backend preview (real
FastAPI + DB, no LLM) reports stable ``kinds`` codes; the panel must render them as localized
sentences, never as raw codes and never as the English wording of an older build.

Both zh and en are checked, then the redacted export is pressed so the real download and success
toast run.
"""

from __future__ import annotations

import json
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    warm_ui_route,
)
from tests.support.redaction_review_e2e import (
    ABSOLUTE_PATH,
    API_TOKEN,
    DISMISS_MIGRATION_JS,
    LEAKY_TEXT,
    ReviewFlow,
    run_review_flow,
)

_PROMPT_SUFFIX = "/system_prompt.md"
_BUTTON_LABEL = {"zh": "导出智能体", "en": "Export agent"}  # agent.exportConfigAction


def _entry_ready_js(locale: str) -> str:
    # Matching the expected label (not any label) keeps the poll from reading the pre-reload page.
    return f"""(() => {{
  const btn = Array.from(document.querySelectorAll('button')).find(
    (b) => (b.textContent || '').trim() === {json.dumps(_BUTTON_LABEL[locale])},
  );
  return {{ ready: !!btn && !btn.disabled, found: !!btn }};
}})()"""


_OPEN_JS = """const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /^(导出智能体|Export agent)$/.test((b.textContent || '').trim()) && !b.disabled,
    );
    if (btn) btn.click();"""

_FLOW = ReviewFlow(
    dialog_title="导出智能体|Export Agent|Export agent",
    entry_ready_js=_entry_ready_js,
    open_js=_OPEN_JS,
    exported_toast={"zh": "智能体包导出成功", "en": "Agent package exported successfully"},
)


def _preview_kinds(api_url: str, agent_id: str) -> list[list[str]]:
    body = http_json("POST", f"{api_url}/api/v1/plugins/export/preview", {"agent_id": agent_id})
    assert isinstance(body, dict), body
    redactions = body.get("redactions")
    assert isinstance(redactions, dict), body
    # The bundle path embeds the expert name (experts/1-<name>/system_prompt.md).
    [findings] = [items for path, items in redactions.items() if path.endswith(_PROMPT_SUFFIX)]
    return [finding["kinds"] for finding in findings]


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_expert_export_review_renders_localized_finding_kinds() -> None:
    """Preview API reports kind codes; the export dialog shows them as localized sentences."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    name = f"kinds-e2e-{uuid.uuid4().hex[:8]}"
    created = http_json("POST", f"{api_url}/api/v1/user-agents", {"name": name, "system_prompt": LEAKY_TEXT})
    assert isinstance(created, dict)
    data = created["data"]
    agent_id = data.get("id") or data.get("agent_id")
    assert isinstance(agent_id, str) and agent_id, created

    try:
        kinds = _preview_kinds(api_url, agent_id)
        assert [API_TOKEN[0]] in kinds and [ABSOLUTE_PATH[0]] in kinds, kinds

        warm_ui_route("/settings")
        # Cold dev-server compile of the agents route can outlast the page-open hydration budget.
        warm_ui_route("/settings/agents", timeout_sec=_warm_ui_parallel_wait_sec(180.0))
        with open_settings_subroute(f"/settings/agents?agentId={agent_id}", timeout_ms=120_000) as (client, page):
            client.evaluate(page, DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page)
            run_review_flow(client, page, _FLOW)
    finally:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
