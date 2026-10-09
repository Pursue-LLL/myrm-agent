"""Chrome E2E: the expert export review shows redaction finding kinds in the user's language.

Real user flow on /settings/agents: open an agent that carries a token and a local path in its
system prompt, press "Export agent", and read the review panel. The backend preview (real
FastAPI + DB, no LLM) reports stable ``kinds`` codes; the panel must render them as localized
sentences, never as raw codes and never as the English wording of an older build.

Both zh and en are checked, then the redacted export is pressed so the real download and success
toast run.

The locale is switched through the ``NEXT_LOCALE`` cookie exactly as the language picker does,
and restored afterwards so the shared E2E browser profile is left as it was found.
"""

from __future__ import annotations

import json
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_PROMPT_SUFFIX = "/system_prompt.md"
_TOKEN = "ghp_E2eKindsCanary0123456789abcdef"
_SYSTEM_PROMPT = f"Call the API with {_TOKEN}.\nThe notes live in /Users/e2e-person/notes.md\n"

# (code, zh sentence, en sentence) from locales/{zh,en}.json common.redactionReview.kinds
_API_TOKEN = ("api_token", "API 密钥或令牌", "API key or token")
_ABSOLUTE_PATH = ("absolute_path", "本机文件路径", "Local file path")

_COOKIE = "NEXT_LOCALE"

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_READ_LOCALE_JS = f"""(() => {{
  const hit = document.cookie.split('; ').find((c) => c.startsWith('{_COOKIE}='));
  return {{ value: hit ? hit.slice({len(_COOKIE) + 1}) : null }};
}})()"""


def _set_locale_js(value: str | None) -> str:
    cookie = f"{_COOKIE}={value}; path=/; max-age=31536000" if value is not None else f"{_COOKIE}=; path=/; max-age=0"
    return f"(() => {{ document.cookie = {json.dumps(cookie)}; location.reload(); return {{ ok: true }}; }})()"


# agent.expertExport.{exportSuccess, actions.exportRedacted} from locales/{zh,en}.json
_EXPORT_REDACTED = {"zh": "导出脱敏版 (安全)", "en": "Export Redacted (Safe)"}
_EXPORT_SUCCESS = {"zh": "智能体包导出成功", "en": "Agent package exported successfully"}
_BUTTON_LABEL = {"zh": "导出智能体", "en": "Export agent"}


def _export_button_js(label: str) -> str:
    # Matching the expected label (not any label) keeps the poll from reading the pre-reload page.
    return f"""(() => {{
  const btn = Array.from(document.querySelectorAll('button')).find(
    (b) => (b.textContent || '').trim() === {json.dumps(label)},
  );
  return {{ ready: !!btn && !btn.disabled, found: !!btn }};
}})()"""


def _review_state_js(*, expect: tuple[str, ...], leaked: tuple[str, ...]) -> str:
    return f"""(() => {{
  const dialog = Array.from(document.querySelectorAll('[role="dialog"]')).find((node) =>
    /导出智能体|Export Agent|Export agent/.test(node.textContent || ''),
  );
  if (!dialog) {{
    // The locale switch reloads the page, which can discard an earlier click; opening is idempotent.
    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /^(导出智能体|Export agent)$/.test((b.textContent || '').trim()) && !b.disabled,
    );
    if (btn) btn.click();
    return {{ ready: false, err: 'export-dialog-not-found', clicked: !!btn, dialogs: document.querySelectorAll('[role="dialog"]').length }};
  }}
  const text = dialog.textContent || '';
  const missing = {json.dumps(list(expect))}.filter((needle) => !text.includes(needle));
  const present = {json.dumps(list(leaked))}.filter((needle) => text.includes(needle));
  return {{
    // The review lists each finding's original line, so the seeded token marks a rendered panel.
    ready: text.includes({json.dumps(_TOKEN)}),
    missing,
    leaked: present,
    text: text.slice(0, 1800),
  }};
}})()"""


def _confirm_export_js(locale: str) -> str:
    """Press the redacted-export button once; done when the dialog has closed after that click.

    The dialog closes only on a successful export (a failure keeps it open under an error toast), so
    closure after the click is the verdict. The success toast is transient, so it is only recorded.
    """
    return f"""(() => {{
  const w = window;
  // innerText skips the inlined <script> payload, which carries every translated string.
  if ((document.body.innerText || '').includes({json.dumps(_EXPORT_SUCCESS[locale])})) w.__kindsToastSeen = true;
  const exportDialogs = () =>
    Array.from(document.querySelectorAll('[role="dialog"]')).filter((node) =>
      /导出智能体|Export Agent|Export agent/.test(node.textContent || ''),
    );
  if (!w.__kindsExportClicked) {{
    const btn = exportDialogs()
      .flatMap((node) => Array.from(node.querySelectorAll('button')))
      .find((b) => (b.textContent || '').trim() === {json.dumps(_EXPORT_REDACTED[locale])} && !b.disabled);
    if (btn) {{ btn.click(); w.__kindsExportClicked = true; }}
    return {{ ready: false, clicked: !!w.__kindsExportClicked }};
  }}
  // Radix flips data-state to "closed" at once; the node itself lingers until its exit animation ends,
  // which never fires while the shared E2E tab is not painted.
  const states = exportDialogs().map((node) => node.getAttribute('data-state'));
  return {{ ready: !states.includes('open'), dialogStates: states, toastSeen: !!w.__kindsToastSeen }};
}})()"""


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
    created = http_json("POST", f"{api_url}/api/v1/user-agents", {"name": name, "system_prompt": _SYSTEM_PROMPT})
    assert isinstance(created, dict)
    data = created["data"]
    agent_id = data.get("id") or data.get("agent_id")
    assert isinstance(agent_id, str) and agent_id, created

    try:
        kinds = _preview_kinds(api_url, agent_id)
        assert [_API_TOKEN[0]] in kinds and [_ABSOLUTE_PATH[0]] in kinds, kinds

        warm_ui_route("/settings")
        with open_settings_subroute(f"/settings/agents?agentId={agent_id}", timeout_ms=120_000) as (client, page):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page)

            previous = client.evaluate(page, _READ_LOCALE_JS, timeout_sec=15.0)
            assert isinstance(previous, dict), previous
            try:
                for locale, own, other in (("zh", 1, 2), ("en", 2, 1)):
                    client.evaluate(page, _set_locale_js(locale), timeout_sec=15.0)
                    button = wait_for_state(client, page, _export_button_js(_BUTTON_LABEL[locale]), timeout_sec=90.0)
                    assert button.get("ready") is True, (locale, button)

                    review = wait_for_state(
                        client,
                        page,
                        _review_state_js(
                            expect=(_API_TOKEN[own], _ABSOLUTE_PATH[own]),
                            leaked=(_API_TOKEN[0], _ABSOLUTE_PATH[0], "kinds.", _API_TOKEN[other], _ABSOLUTE_PATH[other]),
                        ),
                        timeout_sec=90.0,
                    )
                    assert review.get("missing") == [], (locale, review)
                    assert review.get("leaked") == [], (locale, review)

                # The author accepts the redacted package: the real download runs and the dialog closes.
                done = wait_for_state(client, page, _confirm_export_js("en"), timeout_sec=90.0)
                assert done.get("ready") is True, done
            finally:
                client.evaluate(page, _set_locale_js(previous.get("value")), timeout_sec=15.0)
    finally:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}")
