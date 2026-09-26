"""Chrome LIVE E2E: trunk workflow library renders with trunk badges (READ-only)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger  # noqa: E402

_TRUNK_IDS = (
    "trunk-product-triage",
    "trunk-product-delivery",
    "trunk-dev-implement",
    "trunk-bugfix",
    "trunk-product-consolidate",
)

_LIBRARY_TRUNK_JS = """(() => {
  const library = document.querySelector('[data-testid="workflow-template-library"]');
  if (!library) {
    return { ready: false, reason: 'no-library' };
  }
  const text = library.innerText || '';
  const trunkCards = [...library.querySelectorAll('p')]
    .filter((el) => (el.textContent || '').includes('Trunk \\u00b7')).length;
  return { ready: trunkCards > 0, trunkCards, hasLibraryRoot: true };
})()"""


def _wait_trunk_seeded(api_base: str, deadline_sec: float = 120.0) -> None:
    """Trunk seeding runs as a background boot task; poll until visible."""
    deadline = time.monotonic() + deadline_sec
    last: object = None
    while time.monotonic() < deadline:
        body = http_json("GET", f"{api_base}/api/v1/workflow-templates")
        assert isinstance(body, dict)
        templates = body.get("templates")
        assert isinstance(templates, list)
        flagged = {
            str(item.get("templateId")): bool(item.get("isTrunk"))
            for item in templates
            if isinstance(item, dict)
        }
        if all(flagged.get(template_id) is True for template_id in _TRUNK_IDS):
            return
        last = sorted(flagged)
        time.sleep(3.0)
    raise AssertionError(f"trunk templates not seeded: {json.dumps(last, ensure_ascii=False)}")


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_trunk_workflow_library_badges_chrome_e2e(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Settings library lists the five trunk flows with trunk badges (no LLM)."""
    _ = e2e_resource_ledger
    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)
    _wait_trunk_seeded(api_base)

    subroute = "/settings/skills?sub=workflowTemplates"
    ui_base = get_e2e_ui_url().rstrip("/")
    page_url = f"{ui_base}{subroute}"
    with open_settings_subroute(subroute, layout_timeout_sec=120.0) as (client, page):
        ready: dict[str, object] = {}
        for _ in range(3):
            ready = wait_for_state(
                client,
                page,
                _LIBRARY_TRUNK_JS,
                timeout_sec=90.0,
                page_url=page_url,
                blank_heal_mode="direct",
            )
            if ready.get("ready") is True:
                break
            reload_mcp_page(client, page, target_url=page_url, timeout_ms=120_000)
        assert ready.get("ready") is True, json.dumps(ready, indent=2, ensure_ascii=False)
        assert int(ready.get("trunkCards") or 0) >= 5, json.dumps(ready, indent=2, ensure_ascii=False)
