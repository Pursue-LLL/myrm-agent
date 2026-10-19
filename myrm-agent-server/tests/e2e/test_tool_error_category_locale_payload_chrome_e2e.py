"""The WebUI payload ships the tool-error-category labels the progress UI renders.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: shared hot UI attach helpers)

[OUTPUT]
- test_progress_payload_carries_the_output_limit_category: the served shell payload carries
  progressSteps.errorCategories.output_limit with its label

[POS]
progressSteps.errorCategories is rendered from the SSR shell payload built out of
locales/namespaces/; a category whose label never reaches the payload degrades the tool failure
card to the raw enum value, so the newest category is asserted through the real UI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import get_e2e_ui_url, open_mcp_page, wait_for_state

_FRONTEND_LOCALES = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales"
_LOCALES = ("en.json", "zh.json", "ja.json", "zh-TW.json")

_CATEGORY_PAYLOAD_STATE = """(() => {
  const html = document.documentElement.innerHTML;
  const labels = __LABELS__;
  return {
    ready: html.includes('progressSteps') && html.includes('errorCategories'),
    hasKey: html.includes('output_limit'),
    hasLabel: labels.some((label) => html.includes(label)),
  };
})()"""


def _payload_state_expression() -> str:
    return _CATEGORY_PAYLOAD_STATE.replace("__LABELS__", json.dumps(list(_category_labels())))


def _category_labels() -> tuple[str, ...]:
    """Every shipped label for progressSteps.errorCategories.output_limit (locale SSOT)."""
    labels: list[str] = []
    for name in _LOCALES:
        data = json.loads((_FRONTEND_LOCALES / name).read_text("utf-8"))
        label = data.get("progressSteps", {}).get("errorCategories", {}).get("output_limit")
        if isinstance(label, str) and label:
            labels.append(label)
    return tuple(labels)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_progress_payload_carries_the_output_limit_category() -> None:
    """The shell payload served to the browser carries the new category key and one of its labels."""
    labels = _category_labels()
    assert labels, "the locale SSOT must ship a label for output_limit"

    ui_url = get_e2e_ui_url()
    with open_mcp_page(f"{ui_url}/", timeout_ms=90_000) as (client, page):
        state = wait_for_state(
            client,
            page,
            _payload_state_expression(),
            timeout_sec=45.0,
            page_url=f"{ui_url}/",
        )
        assert state.get("hasKey") is True, state
        assert state.get("hasLabel") is True, (labels, state.get("hasKey"))

