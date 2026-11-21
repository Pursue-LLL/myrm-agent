"""Chrome E2E: a shared page runs its CDN chart, and a shared Markdown report is a document that runs nothing it contains.

Real business flow, no mock; the files are registered by the product's own artifact processor and shared by its share API:

    a chat owns a Chart.js page and a Markdown report whose text holds a script tag, an onerror handler and a javascript: link
    -> each is shared the way the share dialog shares it
    -> opened in the browser, the chart page loads Chart.js from its CDN and the canvas holds drawn pixels
    -> the report page shows a heading, bold text and a table as real elements, and the markup the report carries is
       text on the page: no script element, no handler, no javascript: link, and nothing ran
    -> revoking a link makes it answer 404.

Formal run::

    ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_artifact_share_page_chrome_e2e.py::<test_name>
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import partial

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    http_json,
    http_json_once,
    open_mcp_page,
    prepare_e2e_ui_session,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger

_SEED_PATH = "/api/v1/chats/test/seed-artifact-share-fixture"
_ARTIFACTS_PATH = "/api/v1/files/artifacts"
_PAGE_WAIT_SEC = 90.0

_CHART_STATE_JS = """(() => {
  const canvas = document.getElementById('chart');
  const painted = canvas
    ? canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data.some((value) => value !== 0)
    : false;
  return { ready: typeof window.Chart === 'function' && painted, chart: typeof window.Chart, painted };
})()"""

_REPORT_STATE_JS = """(() => {
  const links = Array.from(document.querySelectorAll('a'));
  return {
    ready: Boolean(document.querySelector('h1')),
    heading: document.querySelector('h1')?.textContent?.trim() ?? null,
    hasBold: document.querySelectorAll('strong').length >= 1,
    hasTable: document.querySelectorAll('table').length === 1,
    noScripts: document.querySelectorAll('script').length === 0,
    noHandlers: document.querySelectorAll('[onerror]').length === 0,
    noScriptLinks: links.every((link) => !/^\\s*javascript:/i.test(link.getAttribute('href') ?? '')),
    ran: window.__shareProbe ?? null,
    text: document.body.innerText.slice(0, 800),
  };
})()"""


def _share(api_url: str, artifact_id: str, artifact_type: str) -> str:
    """Share an artifact as the share dialog does; returns the public URL on the backend the test talks to."""
    created = http_json(
        "POST",
        f"{api_url}{_ARTIFACTS_PATH}/{artifact_id}/share-preview",
        body={"ttl_days": 1, "artifact_type": artifact_type},
    )
    assert isinstance(created, dict) and isinstance(created.get("share_path"), str), created
    return f"{api_url}{created['share_path']}"


def _wait_for(condition: Callable[[], bool], failure: str, *, timeout_sec: float = _PAGE_WAIT_SEC) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(1.0)
    pytest.fail(failure)


def _page_state(client: ChromeMcpClient, page: McpPage, expression: str, failure: str) -> dict[str, object]:
    states: list[dict[str, object]] = []

    def ready() -> bool:
        state = client.evaluate(page, expression, timeout_sec=15.0)
        if isinstance(state, dict):
            states.append(state)
        return bool(states) and states[-1].get("ready") is True

    _wait_for(ready, failure)
    return states[-1]


def _answers_not_found(url: str) -> bool:
    return http_json_once("GET", url)[0] == 404


def _revoke(api_url: str, artifact_ids: set[str]) -> None:
    """Revoke the links of these artifacts only: the backend may hold other tests' shares."""
    listed = http_json("GET", f"{api_url}{_ARTIFACTS_PATH}/shares")
    assert isinstance(listed, list), listed
    for record in listed:
        assert isinstance(record, dict), record
        if record.get("artifact_id") in artifact_ids:
            http_json("DELETE", f"{api_url}{_ARTIFACTS_PATH}/shares/{record['id']}")


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a_shared_chart_draws_and_a_shared_report_renders_without_running_its_markup(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    seeded = http_json("POST", f"{api_url}{_SEED_PATH}")
    assert isinstance(seeded, dict), seeded
    e2e_resource_ledger.register("chat", str(seeded["chat_id"]))
    chart_id, report_id = str(seeded["chart_artifact_id"]), str(seeded["report_artifact_id"])
    chart_url = _share(api_url, chart_id, "html")
    report_url = _share(api_url, report_id, "document")

    try:
        with open_mcp_page("about:blank", timeout_ms=90_000) as (client, page):
            client.navigate(page, chart_url, timeout_ms=90_000)
            chart = _page_state(client, page, _CHART_STATE_JS, "the shared chart page never drew its chart")
            assert chart["chart"] == "function" and chart["painted"] is True, chart

            client.navigate(page, report_url, timeout_ms=90_000)
            report = _page_state(client, page, _REPORT_STATE_JS, "the shared report never rendered as a document")
            assert report["heading"] == "Quarterly report", report
            assert report["hasBold"] is True and report["hasTable"] is True, report
            assert report["noScripts"] is True and report["noHandlers"] is True and report["noScriptLinks"] is True, report
            assert report["ran"] is None, f"the report's markup ran: {report}"
            assert "window.__shareProbe" in str(report["text"]), "the report's markup is not shown as text"
    finally:
        _revoke(api_url, {chart_id, report_id})

    for url in (chart_url, report_url):
        _wait_for(partial(_answers_not_found, url), f"a revoked link still answers: {url}", timeout_sec=30.0)
