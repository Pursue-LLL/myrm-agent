"""The WebUI payload ships the tool-error-category labels the progress UI renders.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: shared hot UI attach helpers)
- myrm-agent-frontend/locales/*.json (POS: locale SSOT)

[OUTPUT]
- test_progress_payload_carries_the_output_limit_category: the served shell payload carries
  progressSteps.errorCategories.output_limit plus the label of the page's own locale

[POS]
progressSteps.errorCategories is rendered from the SSR shell payload built out of
locales/namespaces/; a category whose label never reaches the payload degrades the tool failure
card to the raw enum value, so the newest category is asserted through the real UI, in the locale
the page actually runs in. The check stays inside the page so only short scalars cross the bridge.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import get_e2e_ui_url, open_mcp_page, wait_for_state

_FRONTEND_LOCALES = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales"
_LOCALE_FILES = ("en.json", "zh.json", "zh-TW.json", "ja.json", "ko.json", "de.json")

_CATEGORY_PAYLOAD_STATE = """(() => {
  const html = document.documentElement.innerHTML;
  const labels = __LABELS__;
  const lang = (document.documentElement.lang || '').toLowerCase();
  let expected = labels['en'] || '';
  for (const code of ['zh-tw', 'zh', 'ja', 'ko', 'de', 'en']) {
    if (lang.startsWith(code)) {
      expected = labels[code === 'zh-tw' ? 'zh-TW' : code] || labels['en'] || '';
      break;
    }
  }
  return {
    ready: html.includes('progressSteps') && html.includes('errorCategories'),
    hasKey: html.includes('output_limit'),
    lang: lang,
    expected: expected,
    hasExpectedLabel: Boolean(expected) && html.includes(expected),
  };
})()"""


def _category_labels() -> dict[str, str]:
    """progressSteps.errorCategories.output_limit per shipped locale (locale SSOT)."""
    labels: dict[str, str] = {}
    for name in _LOCALE_FILES:
        data = json.loads((_FRONTEND_LOCALES / name).read_text("utf-8"))
        label = data.get("progressSteps", {}).get("errorCategories", {}).get("output_limit")
        if isinstance(label, str) and label:
            labels[name.removesuffix(".json")] = label
    return labels


def _payload_state_expression(labels: dict[str, str]) -> str:
    return _CATEGORY_PAYLOAD_STATE.replace("__LABELS__", json.dumps(labels))


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_progress_payload_carries_the_output_limit_category() -> None:
    """The shell payload carries the new category key and the label of the page's own locale."""
    labels = _category_labels()
    assert labels, "the locale SSOT must ship a label for output_limit"

    ui_url = get_e2e_ui_url()
    with open_mcp_page(f"{ui_url}/", timeout_ms=90_000) as (client, page):
        state = wait_for_state(
            client,
            page,
            _payload_state_expression(labels),
            timeout_sec=45.0,
            page_url=f"{ui_url}/",
        )
        assert state.get("hasKey") is True, state
        assert state.get("hasExpectedLabel") is True, (state.get("lang"), state.get("expected"))
