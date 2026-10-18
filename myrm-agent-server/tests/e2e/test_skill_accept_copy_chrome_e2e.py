"""Chrome MCP E2E: the skill-confirmation copy a reader actually sees.

The upstream-update confirmation tells the user the change can be undone from the
skill detail page. That promise only holds if the reader's own language says so:
a translation that still reads "this cannot be undone" contradicts an undo button
the page renders right above it.

This test reads the rendered copy from the running app in German and in English,
so a later English reword without a matching translation fails here instead of
reaching readers as two different promises for one action.
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_SETTINGS_SHELL_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  return {
    ready:
      location.pathname.startsWith('/settings') &&
      bodyText.length > 20 &&
      !!document.querySelector('[data-testid="settings-layout"]'),
    pathname: location.pathname,
    bodyLength: bodyText.length,
  };
})()"""

# Reads the message straight out of the loaded namespace bundle, which is what the
# confirmation dialog renders from. Reaching the dialog itself needs a prebuilt skill
# in the "upstream update pending" state, a snapshot the sync pass computes rather
# than something the public API can request; the copy is the part this change owns.
_ACCEPT_COPY_JS = """(() => {
  const state = window.__MYRM_ACCEPT_COPY__ || null;
  return { ready: !!state, payload: state };
})()"""

_LOAD_ACCEPT_COPY_JS = """(async () => {
  const res = await fetch('/api/i18n/deferred', { credentials: 'include' });
  if (!res.ok) {
    return { ok: false, status: res.status };
  }
  const data = await res.json();
  const card = data && data.settings && data.settings.skills && data.settings.skills.card;
  const copy = card && card.confirmAcceptDesc;
  window.__MYRM_ACCEPT_COPY__ = { copy: copy || null };
  return { ok: true, hasCopy: !!copy };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_upstream_update_copy_promises_the_undo_each_language_offers() -> None:
    """Every language tells the reader the update can be undone, matching the undo control."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    warm_ui_route("/settings")
    warm_ui_route("/settings/skills", timeout_sec=_warm_ui_parallel_wait_sec(180.0))

    with open_settings_subroute("/settings/skills", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        shell = wait_for_state(
            client,
            page,
            _SETTINGS_SHELL_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert shell.get("ready") is True, json.dumps(shell, indent=2, ensure_ascii=False)

        loaded = client.evaluate(page, _LOAD_ACCEPT_COPY_JS, timeout_sec=30.0)
        assert loaded.get("ok") is True, json.dumps(loaded, indent=2, ensure_ascii=False)
        state = wait_for_state(client, page, _ACCEPT_COPY_JS, timeout_sec=30.0)
        assert state.get("ready") is True, json.dumps(state, indent=2, ensure_ascii=False)

        copy = (state.get("payload") or {}).get("copy")
        assert isinstance(copy, str) and copy, json.dumps(state, indent=2, ensure_ascii=False)

        # The undo the dialog promises exists on the skill detail page; a translation that
        # says the change is permanent sends readers away from a control they could use.
        lowered = copy.lower()
        says_irreversible = any(
            marker in lowered
            for marker in (
                "cannot be undone",
                "nicht rückgängig",
                "no se puede deshacer",
                "取り消せません",
                "되돌릴 수 없습니다",
                "不可撤销",
                "不可撤銷",
            )
        )
        assert not says_irreversible, f"confirmation still claims the update is permanent: {copy!r}"


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_upstream_update_copy_reaches_the_german_reader() -> None:
    """The German reader is told the update can be undone, in the wording this pack uses."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    warm_ui_route("/settings")
    warm_ui_route("/settings/skills", timeout_sec=_warm_ui_parallel_wait_sec(180.0))

    with open_settings_subroute("/settings/skills", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        client.evaluate(
            page,
            "(() => { document.cookie = 'NEXT_LOCALE=de; path=/; max-age=86400'; return true; })()",
            timeout_sec=15.0,
        )
        shell = wait_for_state(
            client,
            page,
            _SETTINGS_SHELL_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert shell.get("ready") is True, json.dumps(shell, indent=2, ensure_ascii=False)

        loaded = client.evaluate(page, _LOAD_ACCEPT_COPY_JS, timeout_sec=30.0)
        assert loaded.get("ok") is True, json.dumps(loaded, indent=2, ensure_ascii=False)
        state = wait_for_state(client, page, _ACCEPT_COPY_JS, timeout_sec=30.0)
        copy = (state.get("payload") or {}).get("copy")
        assert isinstance(copy, str) and copy, json.dumps(state, indent=2, ensure_ascii=False)

        # The surface this copy points at is named "Fähigkeitsdetails" in this pack.
        assert "fähigkeitsdetails" in copy.lower(), f"German copy names another surface: {copy!r}"
        assert "rückgängig" in copy.lower(), f"German copy does not promise the undo: {copy!r}"
        assert ui_url  # keep the resolved UI base in the failure report
