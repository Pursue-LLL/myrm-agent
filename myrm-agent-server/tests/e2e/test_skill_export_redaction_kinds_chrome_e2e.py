"""Chrome E2E: the single-skill export review shows redaction finding kinds in the user's language.

Real user flow on /settings/skills: an installed skill carries a token and a local path in its
SKILL.md; the author finds it in the Installed list, opens its detail sheet, presses "Export", and
reads the review panel. The backend preview (real FastAPI + skill store, no LLM) reports stable
``kinds`` codes; the panel must render them as localized sentences in zh and en, never as raw codes.
Pressing the redacted export then runs the real download and closes the dialog.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import uuid
import zipfile
from http.client import HTTPResponse
from typing import cast

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    guarded_urlopen,
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

# settings.skills.installed.searchPlaceholder
_SEARCH_PLACEHOLDER = {"zh": "搜索已安装技能", "en": "Search installed skills"}

# Radix tabs activate on pointerdown, so a bare click() would not switch them.
_FULL_CLICK_JS = """const fullClick = (el) => {
      const opts = { bubbles: true, cancelable: true, composed: true, button: 0, detail: 1, view: window };
      el.dispatchEvent(new PointerEvent('pointerdown', { ...opts, pointerId: 1, isPrimary: true }));
      el.dispatchEvent(new MouseEvent('mousedown', opts));
      el.dispatchEvent(new PointerEvent('pointerup', { ...opts, pointerId: 1, isPrimary: true }));
      el.dispatchEvent(new MouseEvent('mouseup', opts));
      el.dispatchEvent(new MouseEvent('click', opts));
    };"""

_INSTALLED_TAB_JS = """const tab = Array.from(document.querySelectorAll('[role="tab"]')).find((el) =>
      /^(已安装|Installed)/.test((el.textContent || '').trim()),
    );
    if (tab && tab.getAttribute('aria-selected') !== 'true') fullClick(tab);"""


def _upload_skill(api_url: str, name: str) -> str:
    """Install the skill the way a user's ``.zip`` upload does; returns its id."""
    skill_md = f"---\nname: {name}\ndescription: Redaction review E2E skill\nversion: 1.0.0\n---\n\n# Notes\n\n{LEAKY_TEXT}"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{name}/SKILL.md", skill_md)

    boundary = uuid.uuid4().hex
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}.zip"\r\n'
            "Content-Type: application/zip\r\n\r\n"
        ).encode()
        + buffer.getvalue()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(  # noqa: S310 - loopback E2E only
        f"{api_url.rstrip('/')}/api/v1/skills/upload",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        response = cast(HTTPResponse, guarded_urlopen(request, timeout_sec=60.0))
        with response:
            payload: dict[str, object] = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise AssertionError(f"skill upload failed status={exc.code} body={exc.read()!r}") from exc
    skill_id = payload.get("skill_id")
    assert payload.get("success") is True and isinstance(skill_id, str), payload
    return skill_id


def _preview_kinds(api_url: str, skill_id: str) -> list[list[str]]:
    body = http_json("GET", f"{api_url}/api/v1/skills/{skill_id}/preview")
    assert isinstance(body, dict) and body.get("success") is True, body
    redactions = body.get("redactions")
    assert isinstance(redactions, dict), body
    return [finding["kinds"] for findings in redactions.values() for finding in findings]


def _flow(name: str) -> ReviewFlow:
    def entry_ready_js(locale: str) -> str:
        # The right-language search box proves the page has reloaded into the locale under test.
        return f"""(() => {{
  {_FULL_CLICK_JS}
  {_INSTALLED_TAB_JS}
  const input = Array.from(document.querySelectorAll('input')).find(
    (i) => (i.placeholder || '').startsWith({json.dumps(_SEARCH_PLACEHOLDER[locale])}),
  );
  const tabs = Array.from(document.querySelectorAll('[role="tab"]')).map(
    (el) => `${{(el.textContent || '').trim()}}:${{el.getAttribute('aria-selected')}}`,
  );
  const placeholders = Array.from(document.querySelectorAll('input')).map((i) => i.placeholder);
  return {{ ready: !!input, locale: {json.dumps(locale)}, lang: document.documentElement?.lang ?? '', cookie: document.cookie, tabs, placeholders }};
}})()"""

    # One step toward the dialog per poll: filter the list, open the skill's sheet, press its Export.
    open_js = f"""{_FULL_CLICK_JS}
    const name = {json.dumps(name)};
    const sheet = Array.from(document.querySelectorAll('[role="dialog"]')).find((node) =>
      (node.textContent || '').includes(name),
    );
    if (sheet) {{
      const exportBtn = Array.from(sheet.querySelectorAll('button')).find(
        (b) => /^(导出|Export)$/.test((b.textContent || '').trim()) && !b.disabled,
      );
      if (exportBtn) exportBtn.click();
    }} else {{
      {_INSTALLED_TAB_JS}
      const input = Array.from(document.querySelectorAll('input')).find((i) =>
        /搜索已安装技能|Search installed skills/.test(i.placeholder || ''),
      );
      if (input && input.value !== name) {{
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, name);
        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
      }}
      const card = Array.from(document.querySelectorAll('div[role="presentation"]')).find(
        (node) => node.classList.contains('cursor-pointer') && (node.textContent || '').includes(name),
      );
      if (card) card.click();
    }}"""
    return ReviewFlow(
        dialog_title="导出技能|Export Skill",
        entry_ready_js=entry_ready_js,
        open_js=open_js,
        exported_toast={"zh": "技能导出成功", "en": "Skill exported successfully"},
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_skill_export_review_renders_localized_finding_kinds() -> None:
    """Preview API reports kind codes; the skill export dialog shows them as localized sentences."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    name = f"kinds-skill-{uuid.uuid4().hex[:8]}"
    skill_id = _upload_skill(api_url, name)

    try:
        kinds = _preview_kinds(api_url, skill_id)
        assert [API_TOKEN[0]] in kinds and [ABSOLUTE_PATH[0]] in kinds, kinds

        warm_ui_route("/settings")
        # The skills route compiles slowly on a cold dev server; hydrating it unwarmed times out under load.
        warm_ui_route("/settings/skills", timeout_sec=_warm_ui_parallel_wait_sec(180.0))
        with open_settings_subroute("/settings/skills", timeout_ms=120_000) as (client, page):
            client.evaluate(page, DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page)
            run_review_flow(client, page, _flow(name))
    finally:
        http_json("POST", f"{api_url}/api/v1/skills/discovery/uninstall", {"skill_id": skill_id, "force": True})
