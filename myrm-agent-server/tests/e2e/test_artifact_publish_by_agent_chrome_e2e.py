"""Chrome LIVE E2E: the agent publishes a page it wrote once the user approves, and the chat shows the link.

Real business flow, no mock and no API shortcut for the chat turn itself:

    the user asks for a one-page site and its live link -> the live model writes bakery/index.html with its own tools
    and calls artifact_publish with the page's workspace path
    -> the run parks behind the approval card of that call, which a yolo agent still gets (what leaves the machine is the
       user's decision, and nothing has been published while the card is up)
    -> the user presses Approve -> the platform answers and the model's reply carries the live link, shown once on the page
    -> the files API lists the page once, with one READY publication at that link.

The platform is a public echo endpoint: the server refuses webhook targets on loopback and private networks, so a local receiver
cannot stand in for it. Only the synthetic page asked for below is sent.

Formal run::

    ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_artifact_publish_by_agent_chrome_e2e.py::<test_name>
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

from tests.support.chrome_chat_page_observe import assert_page_settled, wait_for_reply_on_page
from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    prepare_e2e_ui_session,
    wait_e2e_provider_ready,
)
from tests.support.chrome_skill_hooks_approval import approve_cards_until_reply, wait_for_approval_card
from tests.support.chrome_skill_hooks_composer import drive_chat_turn
from tests.support.chrome_skill_hooks_live_e2e import DONE_TOKEN, SkillChat
from tests.support.chrome_skill_hooks_observe import backend_log_offset
from tests.support.e2e_provider_seed import seed_live_e2e_providers
from tests.support.e2e_runtime_guard import E2EResourceLedger

_ECHO_URL = "https://httpbin.org/post"
_ECHO_PROBE_URL = "https://httpbin.org/get"
_TARGETS_PATH = "/api/v1/files/artifacts/hosting/targets"
_ARTIFACTS_PATH = "/api/v1/files/artifacts"
_PAGE_NAME = "index.html"

_REQUEST = (
    f"Make a one-page website for a bakery called Maple Crumb: a single file bakery/{_PAGE_NAME} of fewer than 15 lines, "
    f"with no stylesheet and no script. Then publish that page to my hosting and tell me the live link. "
    f"When you are done, end with a last line of exactly: {DONE_TOKEN}"
)
_AGENT_SYSTEM_PROMPT = "You build small web pages in the workspace and publish them to the user's hosting when the user asks."
_APPROVAL_TIMEOUT_SEC = 300.0
_TOOLS_ASKING_APPROVAL_JS = "window.__MYRM_E2E_CHAT__.toolApprovalSnapshot().tools"


def _require_echo_endpoint() -> None:
    """The publish goes to a public endpoint: fail early, and say why, when this machine cannot reach it."""
    try:
        with urllib.request.urlopen(_ECHO_PROBE_URL, timeout=15.0) as response:  # noqa: S310 - fixed public https url
            reachable = response.status == 200
    except (urllib.error.URLError, TimeoutError):
        reachable = False
    if not reachable:
        pytest.fail(f"the public echo endpoint {_ECHO_PROBE_URL} is unreachable from this machine")


def _create_agent(api_url: str, suffix: str) -> str:
    """A yolo agent: file writes run unasked, so the only card of the turn is the one that has to be there."""
    created = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": f"Publish E2E {suffix}",
            "description": "Artifact publish live E2E probe agent",
            "system_prompt": _AGENT_SYSTEM_PROMPT,
            "skill_ids": [],
            "mcp_ids": [],
            "enabled_builtin_tools": ["code_execute"],
            "security_overrides": {"yoloModeEnabled": True, "yolo_mode_enabled_at": time.time()},
        },
    )
    assert isinstance(created, dict), created
    data = created.get("data")
    agent_id = data.get("id") if isinstance(data, dict) else created.get("id")
    assert isinstance(agent_id, str) and agent_id, created
    return agent_id


def _setup_chat(ledger: E2EResourceLedger, out: Path) -> SkillChat:
    """Providers, the user's hosting target, an agent and an empty chat, all through the product's own API."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm-dev ready --chrome")
    http_json(
        "POST",
        f"{api_url}{_TARGETS_PATH}",
        body={"name": "Bakery site", "provider_type": "http_webhook", "config": {"webhook_url": _ECHO_URL}, "is_default": True},
    )

    suffix = uuid.uuid4().hex[:8]
    agent_id = _create_agent(api_url, suffix)
    ledger.register("agent", agent_id)
    chat_id = f"e2epublish{suffix}"
    created = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={"chat_id": chat_id, "title": "Publish live E2E", "agent_id": agent_id, "action_mode": "agent", "messages": []},
    )
    assert isinstance(created, dict) and created.get("success") is True, created
    ledger.register("chat", chat_id)
    return SkillChat(skill_name="", agent_id=agent_id, chat_id=chat_id, out=out, log_offset=backend_log_offset(api_url))


def _artifacts(api_url: str) -> list[dict[str, object]]:
    listed = http_json("GET", f"{api_url}{_ARTIFACTS_PATH}")
    assert isinstance(listed, dict), listed
    rows = listed.get("artifacts")
    assert isinstance(rows, list), listed
    return [row for row in rows if isinstance(row, dict)]


def _publications(api_url: str) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for artifact in _artifacts(api_url):
        rows = artifact.get("publications")
        assert isinstance(rows, list), artifact
        found.extend(row for row in rows if isinstance(row, dict))
    return found


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_the_agent_publishes_its_page_only_after_the_user_approves(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    _require_echo_endpoint()
    api_url = get_e2e_api_url()
    probe = _setup_chat(e2e_resource_ledger, tmp_path)

    def approve_then_read_the_link(client: ChromeMcpClient, page: McpPage) -> None:
        card = wait_for_approval_card(client, page, timeout_sec=_APPROVAL_TIMEOUT_SEC)
        print(f"E2E_PUBLISH_CARD: {str(card.get('sample'))[:400]!r}", flush=True)
        assert client.evaluate(page, _TOOLS_ASKING_APPROVAL_JS, timeout_sec=15.0) == ["artifact_publish"], card
        assert _publications(api_url) == [], "the page was published while its approval card was still up"

        reply = approve_cards_until_reply(
            client, page, probe, DONE_TOKEN, timeout_sec=_APPROVAL_TIMEOUT_SEC, tolerate_closing_note=True
        )
        assert _ECHO_URL in reply, f"the reply does not carry the live link: {reply!r}"
        wait_for_reply_on_page(client, page, probe, "the reply with the live link is stored but the page did not show it")
        assert_page_settled(client, page)

    drive_chat_turn(get_e2e_ui_url(), probe, _REQUEST, invoke_skill=False, while_open=approve_then_read_the_link)

    pages = [artifact for artifact in _artifacts(api_url) if artifact.get("name") == _PAGE_NAME]
    assert len(pages) == 1, f"expected one {_PAGE_NAME} artifact, got {[a.get('name') for a in _artifacts(api_url)]}"
    publications = pages[0]["publications"]
    assert isinstance(publications, list) and len(publications) == 1, publications
    assert publications[0]["publication_url"] == _ECHO_URL, publications
    assert publications[0]["publication_status"] == "READY", publications
