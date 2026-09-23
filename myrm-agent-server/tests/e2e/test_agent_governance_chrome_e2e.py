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
    # The :3000 WebUI proxies /api to the shared :8080 backend, so every API
    # call in this test must hit the shared base. Otherwise data seeded into
    # an isolate backend is invisible in the browser and vice versa.
    resp = http_json(method, f"http://127.0.0.1:8080{path}", body)
    assert isinstance(resp, dict)
    return resp


def _preclean_agents(prefix: str) -> None:
    """Delete residue from prior interrupted runs (best effort).

    Scoped to the caller run suffix so parallel lane runs cannot delete
    each other's live agents. Stale residue from crashed runs is left for
    manual cleanup (see created[] teardown in the test body).
    """
    try:
        resp = _api("/api/v1/user-agents?page=1&page_size=200")
        items = ((resp.get("data") or {}).get("items")) or []
        for item in items:
            if isinstance(item, dict) and str(item.get("name", "")).startswith(prefix) and not item.get("is_built_in"):
                try:
                    http_json("DELETE", f"http://127.0.0.1:8080/api/v1/user-agents/{item.get('id')}")
                except Exception:
                    pass
    except Exception:
        pass


def _find_agent_id(items: list, name: str) -> str | None:
    for item in items:
        if isinstance(item, dict) and item.get("name") == name:
            return str(item.get("id"))
    return None


def _wait_agent_name(name: str, timeout_sec: float = 60.0) -> str:
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
    _preclean_agents(f"gov-e2e-target-{suffix}")
    _preclean_agents(f"gov-e2e-source-{suffix}")
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

            # T2: create dialog exposes the Responsibility section. The dev UI may
            # still be hydrating when SSR HTML first paints, so retry the click
            # until the client-rendered dialog actually appears.
            opened: dict | None = None
            form: dict | None = None
            for _ in range(8):
                opened = client.evaluate(
                    page,
                    """(() => {
                      const btn = Array.from(document.querySelectorAll('button')).find((el) =>
                        /^(Create Agent|创建智能体)$/.test((el.textContent || '').trim()) && el.offsetParent !== null);
                      if (!btn) return { ok: false };
                      btn.click();
                      return { ok: true, clicked: (btn.textContent || '').trim() };
                    })()""",
                    timeout_sec=15.0,
                )
                if not (isinstance(opened, dict) and opened.get("ok")):
                    time.sleep(3.0)
                    continue
                time.sleep(3.0)
                form = client.evaluate(page, _DIALOG_READY_JS, timeout_sec=15.0)
                if isinstance(form, dict) and form.get("ready") is True:
                    break
            assert isinstance(opened, dict) and opened.get("ok") is True, opened
            assert isinstance(form, dict) and form.get("ready") is True, json.dumps(
                {"opened": opened, "form": form}, ensure_ascii=False
            )

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

        target_id = _wait_agent_name(target_name)
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

        # T5: temp source shares two skills with the target, then the whole merge
        # runs inside the browser wizard (preview -> confirm -> execute -> undo).
        src_resp = _api(
            "/api/v1/user-agents",
            "POST",
            {"name": source_name, "skill_ids": ["e2e-skill-a", "e2e-skill-b", "e2e-skill-c"]},
        )
        source_id = str((src_resp.get("data") or {}).get("id") or "")
        assert source_id, src_resp
        created.append(source_id)
        _api(f"/api/v1/user-agents/{target_id}", "PUT", {"skill_ids": ["e2e-skill-a", "e2e-skill-b"]})

        with open_mcp_page(agents_url) as (client, page):
            navigate_mcp_page(client, page, agents_url, timeout_ms=90_000)
            dismiss_blocking_modals(client, page)

            # T5a: overlap row appears with a Merge button. Note: the orphan
            # section renders first, so scan every matching row, not rows[0].
            row_probe = """(() => {
              const rows = Array.from(document.querySelectorAll('li')).filter((el) =>
                (el.textContent || '').includes('__SRC__'));
              const btn = rows.flatMap((r) => Array.from(r.querySelectorAll('button'))).find((b) =>
                /^(Merge|合并)$/.test((b.textContent || '').trim()));
              return { ready: !!btn };
            })()""".replace("__SRC__", source_name)
            try:
                row = wait_for_state(
                    client,
                    page,
                    row_probe,
                    timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                )
            except Exception as wait_err:
                dbg = _api("/api/v1/agents/governance/overview").get("data") or {}
                dom = client.evaluate(
                    page,
                    """(() => {
                      const sec = document.querySelector('section[aria-label="Agent governance"]');
                      return {
                        panel: !!sec,
                        panelText: sec ? (sec.innerText || '').slice(0, 600) : null,
                        liCount: document.querySelectorAll('li').length,
                      };
                    })()""",
                    timeout_sec=15.0,
                )
                raise AssertionError(
                    f"overlap row missing: wait_err={wait_err!r} "
                    f"total={dbg.get('total')} orphans={len(dbg.get('orphans', []))} "
                    f"overlaps={json.dumps(dbg.get('overlaps', []), ensure_ascii=False)[:800]} "
                    f"dom={json.dumps(dom, ensure_ascii=False)[:900]}"
                ) from wait_err
            assert row.get("ready") is True, json.dumps(row, ensure_ascii=False)
            clicked = client.evaluate(
                page,
                """(() => {
                  const rows = Array.from(document.querySelectorAll('li')).filter((el) =>
                    (el.textContent || '').includes('__SRC__'));
                  const btn = rows.flatMap((r) => Array.from(r.querySelectorAll('button'))).find((b) =>
                    /^(Merge|合并)$/.test((b.textContent || '').trim()));
                  if (!btn) return { ok: false };
                  btn.click();
                  return { ok: true };
                })()""".replace("__SRC__", source_name),
                timeout_sec=15.0,
            )
            assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

            # T5b: wizard opens; run preview and check the skill diff.
            wiz = wait_for_state(
                client,
                page,
                """(() => {
                  const dlg = document.querySelector('[role=dialog]');
                  if (!dlg) return { ready: false };
                  const preview = Array.from(dlg.querySelectorAll('button')).find((b) =>
                    /^(Preview changes|预览变更)$/.test((b.textContent || '').trim()));
                  return { ready: !!preview };
                })()""",
                timeout_sec=60.0,
            )
            assert wiz.get("ready") is True, json.dumps(wiz, ensure_ascii=False)

            # T5b0: pin the target select to the UI-created agent (pair order
            # from the overlap detector is nondeterministic).
            picked = client.evaluate(
                page,
                """(() => {
                  const dlg = document.querySelector('[role=dialog]');
                  const triggers = Array.from(dlg.querySelectorAll('[role=combobox]'));
                  if (triggers.length < 2) return { ok: false, reason: 'no-triggers' };
                  triggers[1].click();
                  return { ok: true };
                })()""",
                timeout_sec=15.0,
            )
            assert isinstance(picked, dict) and picked.get("ok") is True, picked
            chosen = wait_for_state(
                client,
                page,
                f"""(() => {{
                  const opt = Array.from(document.querySelectorAll('[role=option]')).find((el) =>
                    (el.textContent || '').trim() === '{target_name}');
                  if (!opt) return {{ ready: false }};
                  opt.click();
                  return {{ ready: true }};
                }})()""",
                timeout_sec=30.0,
            )
            assert chosen.get("ready") is True, json.dumps(chosen, ensure_ascii=False)
            picked_src = client.evaluate(
                page,
                """(() => {
                  const dlg = document.querySelector('[role=dialog]');
                  const triggers = Array.from(dlg.querySelectorAll('[role=combobox]'));
                  if (triggers.length < 2) return { ok: false, reason: 'no-triggers' };
                  triggers[0].click();
                  return { ok: true };
                })()""",
                timeout_sec=15.0,
            )
            assert isinstance(picked_src, dict) and picked_src.get("ok") is True, picked_src
            chosen_src = wait_for_state(
                client,
                page,
                f"""(() => {{
                  const opt = Array.from(document.querySelectorAll('[role=option]')).find((el) =>
                    (el.textContent || '').trim() === '{source_name}');
                  if (!opt) return {{ ready: false }};
                  opt.click();
                  return {{ ready: true }};
                }})()""",
                timeout_sec=30.0,
            )
            assert chosen_src.get("ready") is True, json.dumps(chosen_src, ensure_ascii=False)
            client.evaluate(
                page,
                """(() => {
                  const dlg = document.querySelector('[role=dialog]');
                  Array.from(dlg.querySelectorAll('button')).find((b) =>
                    /^(Preview changes|预览变更)$/.test((b.textContent || '').trim())).click();
                  return { ok: true };
                })()""",
                timeout_sec=15.0,
            )
            diff = wait_for_state(
                client,
                page,
                """(() => {
                  const dlg = document.querySelector('[role=dialog]');
                  const txt = dlg ? (dlg.innerText || '') : '';
                  const bodyTxt = document.body.innerText || '';
                  if (txt.includes('e2e-skill-c')) {
                    return { ready: true };
                  }
                  const toast = Array.from(document.querySelectorAll('[data-sonner-toast], [role=status]')).map((el) => (el.textContent || '').slice(0, 200));
                  return { ready: false, dlg: txt.slice(0, 400), toast };
                })()""",
                timeout_sec=60.0,
            )
            assert diff.get("ready") is True, json.dumps(diff, ensure_ascii=False)

            # T5c: type the target name and execute the merge in the browser.
            fill = client.evaluate(
                page,
                f"""(() => {{
                  const input = document.getElementById('merge-confirm');
                  if (!input) return {{ ok: false }};
                  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                  setter.call(input, {json.dumps(target_name)});
                  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                  const exec = Array.from(document.querySelectorAll('[role=dialog] button')).find((b) =>
                    /^(Merge now|立即合并)$/.test((b.textContent || '').trim()));
                  if (!exec || exec.disabled) return {{ ok: false, reason: 'no-exec' }};
                  exec.click();
                  return {{ ok: true }};
                }})()""",
                timeout_sec=15.0,
            )
            assert isinstance(fill, dict) and fill.get("ok") is True, fill
            undone_state = wait_for_state(
                client,
                page,
                """(() => {
                  const dlg = document.querySelector('[role=dialog]');
                  if (!dlg) return { ready: false, reason: 'no-dialog' };
                  const undo = Array.from(dlg.querySelectorAll('button')).find((b) =>
                    /^(Restore target|还原目标)$/.test((b.textContent || '').trim()));
                  return { ready: !!undo };
                })()""",
                timeout_sec=90.0,
            )
            assert undone_state.get("ready") is True, json.dumps(undone_state, ensure_ascii=False)

            # T5d: undo in the browser rolls the target back.
            client.evaluate(
                page,
                """(() => {
                  const dlg = document.querySelector('[role=dialog]');
                  Array.from(dlg.querySelectorAll('button')).find((b) =>
                    /^(Restore target|还原目标)$/.test((b.textContent || '').trim())).click();
                  return { ok: true };
                })()""",
                timeout_sec=15.0,
            )

        merged = _api(f"/api/v1/user-agents/{target_id}").get("data") or {}
        assert "e2e-skill-c" not in (merged.get("skill_ids") or []), merged
        created.remove(source_id)
    finally:
        # T6: cleanup leaves no residue (same shared base as creation/list).
        for agent_id in created:
            try:
                _api(f"/api/v1/user-agents/{agent_id}", method="DELETE")
            except Exception:
                pass
