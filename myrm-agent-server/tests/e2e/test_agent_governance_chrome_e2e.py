"""Chrome E2E: Agent responsibility-unit governance end to end.

Lane-B (frontend/page contract) + real API chain, zero mocks:
  T1 - /agents page renders the agent list.
  T2 - The Create dialog exposes the Responsibility section (scope/owner/checklist).
  T3 - Saving persists responsibility_scope/owner_label/acceptance_criteria
       (POST /api/v1/user-agents then GET round-trip).
  T4 - GET /governance/overview lists the new agent with its asset row.
  T5 - Merge dry-run + execute moves config from a temp source into the new
       agent, then cleanup removes the merged target.
  T6 - Cleanup removes every temp agent (no residue).

Prerequisite:
  ./myrm isolate <id> ready --chrome
"""

from __future__ import annotations

import json
import time
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    navigate_mcp_page,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_DIALOG_READY_JS = """(() => {
  const scope = document.getElementById('responsibility_scope');
  const owner = document.getElementById('owner_label');
  const criteria = document.getElementById('acceptance_criteria');
  const name = Array.from(document.querySelectorAll('input')).find((el) =>
    /e\\.g\\. Code Reviewer|例如/.test(el.placeholder || ''),
  );
  return {
    ready: !!(scope && owner && criteria && name),
    hasScope: !!scope,
    hasOwner: !!owner,
    hasCriteria: !!criteria,
    hasName: !!name,
  };
})()"""

_FILL_AND_SAVE_JS = """((args) => {
  const setValue = (el, value) => {
    const setter = Object.getOwnPropertyDescriptor(el.__proto__, 'value')?.set
      || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    const proto = el.tagName === 'TEXTAREA'
      ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const realSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    (setter || realSetter).call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const name = Array.from(document.querySelectorAll('input')).find((el) =>
    /e\\.g\\. Code Reviewer|例如/.test(el.placeholder || ''),
  );
  if (!name) return { ok: false, reason: 'no-name' };
  setValue(name, args.name);
  setValue(document.getElementById('responsibility_scope'), args.scope);
  setValue(document.getElementById('owner_label'), args.owner);
  setValue(document.getElementById('acceptance_criteria'), args.criteria);
  const save = Array.from(document.querySelectorAll('button')).find((el) =>
    /^(Save|保存)$/.test((el.textContent || '').trim()),
  );
  if (!save || save.disabled) return { ok: false, reason: 'no-save' };
  save.click();
  return { ok: true };
})(__ARGS__)"""


def _api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    resp = http_json(method, f"{get_e2e_api_url()}{path}", body)
    assert isinstance(resp, dict)
    return resp


def _find_agent_id(items: list, name: str) -> str | None:
    for item in items:
        if isinstance(item, dict) and item.get("name") == name:
            return str(item.get("id"))
    return None


def _wait_agent_name(api_url: str, name: str, timeout_sec: float = 60.0) -> str:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        resp = _api("/api/v1/user-agents?page=1&page_size=100")
        items = ((resp.get("data") or {}).get("items")) or []
        found = _find_agent_id(items, name)
        if found:
            return found
        time.sleep(2.0)
    raise AssertionError(f"agent {name!r} never appeared in list")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_governance_responsibility_create_and_merge_via_ui() -> None:
    """Responsibility fields survive the /agents create flow; merge moves config."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    suffix = uuid.uuid4().hex[:8]
    target_name = f"gov-e2e-target-{suffix}"
    source_name = f"gov-e2e-source-{suffix}"
    created: list[str] = []
    try:
        warm_ui_route("/agents")
        agents_url = f"{ui_url}/agents"
        with open_mcp_page(agents_url) as (client, page):
            navigate_mcp_page(client, page, agents_url, timeout_ms=90_000)
            dismiss_blocking_modals(client, page)

            # T1: list renders.
            listed = wait_for_state(
                client,
                page,
                "(() => ({ ready: document.body.innerText.includes('My Agents') || document.body.innerText.includes('我的智能体') }))()",
                timeout_sec=_warm_ui_parallel_wait_sec(60.0),
            )
            assert listed.get("ready") is True, json.dumps(listed, ensure_ascii=False)

            # T2: create dialog exposes the Responsibility section.
            opened = client.evaluate(
                page,
                """(() => {
                  const btns = Array.from(document.querySelectorAll('button')).filter((el) =>
                    /^(Create Agent|创建智能体)$/.test((el.textContent || '').trim()));
                  const btn = btns.find((el) => el.offsetParent !== null) || btns[0];
                  if (!btn) return { ok: false, count: 0 };
                  btn.click();
                  return { ok: true, count: btns.length };
                })()""",
                timeout_sec=15.0,
            )
            assert isinstance(opened, dict) and opened.get("ok") is True, opened
            form = wait_for_state(client, page, _DIALOG_READY_JS, timeout_sec=60.0)
            assert form.get("ready") is True, json.dumps(form, ensure_ascii=False)

            # T3: fill + save through the real dialog.
            js = _FILL_AND_SAVE_JS.replace(
                "__ARGS__",
                json.dumps(
                    {
                        "name": target_name,
                        "scope": "Owns e2e verification replies",
                        "owner": "e2e-bot",
                        "criteria": "Reply recorded\nNo manual step",
                    }
                ),
            )
            saved = client.evaluate(page, js, timeout_sec=20.0)
            assert isinstance(saved, dict) and saved.get("ok") is True, saved

        target_id = _wait_agent_name(api_url, target_name)
        created.append(target_id)
        detail = _api(f"/api/v1/user-agents/{target_id}").get("data") or {}
        assert detail.get("responsibility_scope") == "Owns e2e verification replies", detail
        assert detail.get("owner_label") == "e2e-bot", detail
        assert detail.get("acceptance_criteria") == ["Reply recorded", "No manual step"], detail

        # T4: governance overview lists the new agent.
        overview = _api("/api/v1/agents/governance/overview").get("data") or {}
        rows = {a["id"]: a for a in overview.get("agents", []) if isinstance(a, dict)}
        assert target_id in rows, f"target missing from overview: {sorted(rows)}"
        assert rows[target_id]["responsibility_scope"] == "Owns e2e verification replies"

        # T5: temp source via API, then dry-run + execute a real merge.
        src_resp = _api("/api/v1/user-agents", "POST", {"name": source_name, "skill_ids": ["e2e-skill"]})
        source_id = str((src_resp.get("data") or {}).get("id") or "")
        assert source_id, src_resp
        created.append(source_id)

        dry = _api(
            "/api/v1/agents/governance/merge/dry-run",
            "POST",
            {"source_id": source_id, "target_id": target_id},
        ).get("data") or {}
        assert dry.get("ok") is True, dry
        assert "e2e-skill" in ((dry.get("plan") or {}).get("move_skills") or []), dry

        executed = _api(
            "/api/v1/agents/governance/merge/execute",
            "POST",
            {"source_id": source_id, "target_id": target_id, "confirm_name": target_name},
        ).get("data") or {}
        assert executed.get("ok") is True, executed
        created.remove(source_id)

        merged = _api(f"/api/v1/user-agents/{target_id}").get("data") or {}
        assert "e2e-skill" in (merged.get("skill_ids") or []), merged
    finally:
        # T6: cleanup leaves no residue.
        for agent_id in created:
            try:
                http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
            except Exception:
                pass
