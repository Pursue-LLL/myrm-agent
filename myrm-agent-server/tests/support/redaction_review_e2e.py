"""The browser side of the export-review Chrome E2Es: what an author does in the redaction review.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: CDP page helpers)

[OUTPUT]
- LEAKY_TEXT / TOKEN / API_TOKEN / ABSOLUTE_PATH: a text carrying one key and one local path, and the wording its findings get
- ReviewFlow: what differs between export dialogs (title, how a user reaches it, button and toast wording)
- run_review_flow(): per locale, read the localized finding kinds in the dialog, then press the redacted export
- DISMISS_MIGRATION_JS: stops the migration banner from covering the page

[POS]
Shared by the expert-export and skill-export Chrome E2Es. Both dialogs render the same ``RedactionReview``, so
the reading of the panel lives here once; only the way into each dialog differs. The locale is switched through the
``NEXT_LOCALE`` cookie exactly as the language picker does, and restored afterwards so the shared E2E browser
profile is left as it was found.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, reload_mcp_page, wait_for_state

TOKEN = "ghp_E2eKindsCanary0123456789abcdef"
LEAKY_TEXT = f"Call the API with {TOKEN}.\nThe notes live in /Users/e2e-person/notes.md\n"

# (code, zh sentence, en sentence) from locales/{zh,en}.json common.redactionReview.kinds
API_TOKEN = ("api_token", "API 密钥或令牌", "API key or token")
ABSOLUTE_PATH = ("absolute_path", "本机文件路径", "Local file path")

# Both export dialogs label the two decisions alike (locales/{zh,en}.json *.actions.exportRedacted).
EXPORT_REDACTED = {"zh": "导出脱敏版 (安全)", "en": "Export Redacted (Safe)"}

_COOKIE = "NEXT_LOCALE"
_LOCALES = (("zh", 1, 2), ("en", 2, 1))  # (locale, own sentence index, other language's index)

DISMISS_MIGRATION_JS = """(() => {
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


@dataclass(frozen=True)
class ReviewFlow:
    """One export dialog as a user meets it."""

    dialog_title: str  # JS regex source matching the dialog's title in every locale
    entry_ready_js: Callable[[str], str]  # locale -> expression whose ``ready`` says the entry point is rendered
    open_js: str  # JS statements that click one step towards the dialog; run while it is absent (idempotent)
    exported_toast: Mapping[str, str]  # locale -> the success sentence shown after the export


def _switch_locale(client: ChromeMcpClient, page: McpPage, value: str | None) -> None:
    """Set the language cookie as the picker does, then reload through the harness.

    The harness reload waits for the load and re-binds the private backend to the page; a bare
    ``location.reload()`` returns at once and leaves the next evaluate racing the navigation.
    """
    cookie = f"{_COOKIE}={value}; path=/; max-age=31536000" if value is not None else f"{_COOKIE}=; path=/; max-age=0"
    client.evaluate(page, f"(() => {{ document.cookie = {json.dumps(cookie)}; return {{ ok: true }}; }})()", timeout_sec=15.0)
    reload_mcp_page(client, page, timeout_ms=90_000)


def _review_state_js(flow: ReviewFlow, *, expect: tuple[str, ...], leaked: tuple[str, ...]) -> str:
    return f"""(() => {{
  const dialog = Array.from(document.querySelectorAll('[role="dialog"]')).find((node) =>
    /{flow.dialog_title}/.test(node.textContent || ''),
  );
  if (!dialog) {{
    // The locale switch reloads the page, which can discard an earlier click; opening is idempotent.
    {flow.open_js}
    return {{ ready: false, err: 'export-dialog-not-found' }};
  }}
  const text = dialog.textContent || '';
  const missing = {json.dumps(list(expect))}.filter((needle) => !text.includes(needle));
  const present = {json.dumps(list(leaked))}.filter((needle) => text.includes(needle));
  return {{
    // The review lists each finding's original line, so the seeded token marks a rendered panel.
    ready: text.includes({json.dumps(TOKEN)}),
    missing,
    leaked: present,
    text: text.slice(0, 1800),
  }};
}})()"""


def _confirm_export_js(flow: ReviewFlow, locale: str) -> str:
    """Press the redacted-export button once; done when the dialog has closed after that click.

    The dialog closes only on a successful export (a failure keeps it open under an error toast), so
    closure after the click is the verdict. The success toast is transient, so it is only recorded.
    """
    return f"""(() => {{
  const w = window;
  // innerText skips the inlined <script> payload, which carries every translated string.
  if ((document.body.innerText || '').includes({json.dumps(flow.exported_toast[locale])})) w.__kindsToastSeen = true;
  const exportDialogs = () =>
    Array.from(document.querySelectorAll('[role="dialog"]')).filter((node) =>
      /{flow.dialog_title}/.test(node.textContent || ''),
    );
  if (!w.__kindsExportClicked) {{
    const btn = exportDialogs()
      .flatMap((node) => Array.from(node.querySelectorAll('button')))
      .find((b) => (b.textContent || '').trim() === {json.dumps(EXPORT_REDACTED[locale])} && !b.disabled);
    if (btn) {{ btn.click(); w.__kindsExportClicked = true; }}
    return {{ ready: false, clicked: !!w.__kindsExportClicked }};
  }}
  // Radix flips data-state to "closed" at once; the node itself lingers until its exit animation ends,
  // which never fires while the shared E2E tab is not painted.
  const states = exportDialogs().map((node) => node.getAttribute('data-state'));
  return {{ ready: !states.includes('open'), dialogStates: states, toastSeen: !!w.__kindsToastSeen }};
}})()"""


def run_review_flow(client: ChromeMcpClient, page: McpPage, flow: ReviewFlow) -> None:
    """Read the review in zh and en, then accept the redacted package; restores the browser's locale."""
    previous = client.evaluate(page, _READ_LOCALE_JS, timeout_sec=15.0)
    assert isinstance(previous, dict), previous
    try:
        for locale, own, other in _LOCALES:
            _switch_locale(client, page, locale)
            entry = wait_for_state(client, page, flow.entry_ready_js(locale), timeout_sec=90.0)
            assert entry.get("ready") is True, (locale, entry)

            review = wait_for_state(
                client,
                page,
                _review_state_js(
                    flow,
                    expect=(API_TOKEN[own], ABSOLUTE_PATH[own]),
                    leaked=(API_TOKEN[0], ABSOLUTE_PATH[0], "kinds.", API_TOKEN[other], ABSOLUTE_PATH[other]),
                ),
                timeout_sec=90.0,
            )
            assert review.get("missing") == [], (locale, review)
            assert review.get("leaked") == [], (locale, review)

        # The author accepts the redacted package: the real download runs and the dialog closes.
        done = wait_for_state(client, page, _confirm_export_js(flow, "en"), timeout_sec=90.0)
        assert done.get("ready") is True, done
    finally:
        _switch_locale(client, page, previous.get("value"))
