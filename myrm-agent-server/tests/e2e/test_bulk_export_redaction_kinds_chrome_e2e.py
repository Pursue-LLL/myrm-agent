"""Chrome E2E: the bulk export wizard shows redaction finding kinds, and its own wording, in the user's language.

Real user flow on /settings/agents: press "Bulk export", keep the preselected agents (one carries a
token and a local path in its system prompt), go to the next step and read the review panel. The
backend preview (real FastAPI + DB, no LLM) reports stable ``kinds`` codes; the panel must render them
as localized sentences in zh and en, and the wizard's own buttons and titles must follow the language
too (they were once hard-coded Chinese). Pressing the redacted export then runs the real download.
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

_ENTRY_LABEL = {"zh": "批量导出", "en": "Bulk export"}  # agent.expertExport.bulk.entry
_NEXT = "^(下一步：分析依赖闭包|Next: analyze dependencies)"  # agent.expertExport.bulk.next
_PROMPT_SUFFIX = "/system_prompt.md"


def _entry_ready_js(locale: str) -> str:
    # Matching the expected label (not any label) keeps the poll from reading the pre-reload page.
    return f"""(() => {{
  const btn = Array.from(document.querySelectorAll('button')).find(
    (b) => (b.textContent || '').trim() === {json.dumps(_ENTRY_LABEL[locale])},
  );
  return {{ ready: !!btn && !btn.disabled, found: !!btn }};
}})()"""


_OPEN_JS = """const entry = Array.from(document.querySelectorAll('button')).find((b) =>
      /^(批量导出|Bulk export)$/.test((b.textContent || '').trim()) && !b.disabled,
    );
    if (entry) entry.click();"""

# The wizard opens on the selection step; the review exists only after "next" (enabled once agents are listed).
_ADVANCE_JS = f"""const next = Array.from(dialog.querySelectorAll('button')).find((b) =>
      new RegExp({json.dumps(_NEXT)}).test((b.textContent || '').trim()) && !b.disabled,
    );
    if (next) next.click();"""

_FLOW = ReviewFlow(
    dialog_title="批量导出与资产迁移|Bulk export and asset migration",
    entry_ready_js=_entry_ready_js,
    open_js=_OPEN_JS,
    exported_toast={"zh": "智能体包导出成功", "en": "Agent package exported successfully"},
    advance_js=_ADVANCE_JS,
)


def _preview_kinds(api_url: str, agent_id: str) -> list[list[str]]:
    body = http_json("POST", f"{api_url}/api/v1/plugins/export/batch/preview", {"agent_ids": [agent_id]})
    assert isinstance(body, dict), body
    redactions = body.get("redactions")
    assert isinstance(redactions, dict), body
    [findings] = [items for path, items in redactions.items() if path.endswith(_PROMPT_SUFFIX)]
    return [finding["kinds"] for finding in findings]


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_bulk_export_review_renders_localized_finding_kinds() -> None:
    """Preview API reports kind codes; the bulk wizard shows them, and its own wording, localized."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    name = f"kinds-bulk-{uuid.uuid4().hex[:8]}"
    created = http_json("POST", f"{api_url}/api/v1/user-agents", {"name": name, "system_prompt": LEAKY_TEXT})
    assert isinstance(created, dict)
    data = created["data"]
    agent_id = data.get("id") or data.get("agent_id")
    assert isinstance(agent_id, str) and agent_id, created

    try:
        kinds = _preview_kinds(api_url, agent_id)
        assert [API_TOKEN[0]] in kinds and [ABSOLUTE_PATH[0]] in kinds, kinds

        warm_ui_route("/settings")
        warm_ui_route("/settings/agents", timeout_sec=_warm_ui_parallel_wait_sec(180.0))
        with open_settings_subroute("/settings/agents", timeout_ms=120_000) as (client, page):
            client.evaluate(page, DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page)
            run_review_flow(client, page, _FLOW)
    finally:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
