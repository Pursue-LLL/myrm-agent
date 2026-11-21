"""Chrome E2E: the hosting settings page offers the providers that exist, keeps a webhook's secret out of every response, and forgets it on delete.

Real business flow through the WebUI, no mock; only the checks read the API:

    open Settings > Hosting Targets -> the add card offers Vercel and HTTP Webhook and nothing else
    -> add an HTTP Webhook target, fill its URL and auth header, press Save target
    -> the API lists the URL but the secret appears in no response, and the credentials are reported as configured
    -> reload the page: the URL is back and the secret field is empty
    -> delete the target: it is gone from the page and its credentials are gone from the API.

Formal run::

    ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_hosting_settings_chrome_e2e.py::<test_name>
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    http_json_once,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_settings_layout,
    wait_for_state,
    warm_ui_route,
)

_HOSTING_ROUTE = "/settings/hosting"
_TARGETS_PATH = "/api/v1/files/artifacts/hosting/targets"
_WEBHOOK_URL = "https://hooks.example.com/publish"

# The section the page keeps open for the active tab; the add card's provider buttons are the only buttons of its 2-column grid.
_SECTION = 'document.querySelector(\'[data-section="hosting"][data-active="true"]\')'

_PROVIDERS_JS = f"""(() => {{
  const section = {_SECTION};
  const text = section?.innerText || '';
  const labels = section
    ? Array.from(section.querySelectorAll('div.grid-cols-2 > button[type="button"]')).map((b) => (b.textContent || '').trim())
    : [];
  return {{ ready: Boolean(section) && /Hosting Targets|托管目标/.test(text) && labels.length > 0, labels, text: text.slice(0, 800) }};
}})()"""

# React reads the chosen provider when the add button is pressed, so the page gets a moment between the two clicks.
_ADD_WEBHOOK_TARGET_JS = f"""(() => {{
  const section = {_SECTION};
  const buttons = section ? Array.from(section.querySelectorAll('button')) : [];
  const provider = buttons.find((b) => (b.textContent || '').trim() === 'HTTP Webhook');
  const add = buttons.find((b) => /^(Add target|添加目标)$/.test((b.textContent || '').trim()));
  if (!provider || !add) return {{ ok: false, err: 'add-card-missing' }};
  provider.click();
  return new Promise((resolve) => setTimeout(() => {{ add.click(); resolve({{ ok: true }}); }}, 400));
}})()"""

# The webhook target's card is the one with a webhook URL field; its id is the field id without the suffix.
_WEBHOOK_CARD_JS = f"""(() => {{
  const section = {_SECTION};
  const fields = section ? Array.from(section.querySelectorAll('input[id$="-webhook_url"]')) : [];
  return {{ ready: fields.length === 1, count: fields.length, id: fields[0] ? fields[0].id.slice(0, -'-webhook_url'.length) : null }};
}})()"""


def _fill_and_save_js(target_id: str, secret: str) -> str:
    """Type the URL, the auth header and the secret into the target's fields as a user does, then press Save target."""
    return f"""(() => {{
  const fill = (id, value) => {{
    const input = document.getElementById(id);
    if (!input) return false;
    Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
    return true;
  }};
  const filled = [
    fill({json.dumps(f"{target_id}-webhook_url")}, {json.dumps(_WEBHOOK_URL)}),
    fill({json.dumps(f"{target_id}-cred-auth_header")}, 'X-Publish-Key'),
    fill({json.dumps(f"{target_id}-cred-auth_value")}, {json.dumps(secret)}),
  ];
  const name = document.getElementById({json.dumps(f"name-{target_id}")});
  const card = name ? name.closest('div.rounded-2xl') : null;
  const save = card ? Array.from(card.querySelectorAll('button')).find((b) => /^(Save target|保存目标)$/.test((b.textContent || '').trim())) : null;
  if (!filled.every(Boolean) || !save) return {{ ok: false, filled, hasSave: Boolean(save) }};
  return new Promise((resolve) => setTimeout(() => {{ save.click(); resolve({{ ok: true }}); }}, 400));
}})()"""


def _field_values_js(target_id: str) -> str:
    return f"""(() => {{
  const value = (id) => document.getElementById(id)?.value ?? null;
  const url = value({json.dumps(f"{target_id}-webhook_url")});
  return {{ ready: url !== null, url, secret: value({json.dumps(f"{target_id}-cred-auth_value")}) }};
}})()"""


def _delete_target_js(target_id: str) -> str:
    return f"""(() => {{
  const name = document.getElementById({json.dumps(f"name-{target_id}")});
  const card = name ? name.closest('div.rounded-2xl') : null;
  const trash = card ? Array.from(card.querySelectorAll('button')).find((b) => b.querySelector('svg.lucide-trash-2, svg.lucide-trash2')) : null;
  if (!trash) return {{ ok: false, err: 'delete-button-missing' }};
  trash.click();
  return {{ ok: true }};
}})()"""


def _card_gone_js(target_id: str) -> str:
    return f"(() => ({{ ready: Boolean({_SECTION}) && document.getElementById({json.dumps(f'name-{target_id}')}) === null }}))()"


def _open_hosting_page(client: ChromeMcpClient, page: McpPage, url: str) -> None:
    client.navigate(page, url, timeout_ms=90_000)
    dismiss_blocking_modals(client, page, recover_url=url)
    wait_for_settings_layout(client, page, page_url=url, timeout_sec=60.0)


def _targets(api_url: str) -> list[dict[str, object]]:
    listed = http_json("GET", f"{api_url}{_TARGETS_PATH}")
    assert isinstance(listed, dict), listed
    targets = listed.get("targets")
    assert isinstance(targets, list), listed
    return [target for target in targets if isinstance(target, dict)]


def _credentials(api_url: str, target_id: str) -> dict[str, object]:
    status, body = http_json_once("GET", f"{api_url}{_TARGETS_PATH}/{target_id}/credentials")
    assert status in (200, 404), (status, body)
    return body if isinstance(body, dict) else {}


def _wait_for(condition: Callable[[], bool], failure: str, *, timeout_sec: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(1.0)
    pytest.fail(failure)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a_webhook_target_is_added_saved_without_echoing_its_secret_and_deleted() -> None:
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    hosting_url = f"{get_e2e_ui_url().rstrip('/')}{_HOSTING_ROUTE}"
    secret = f"E2E-HOSTING-SECRET-{uuid.uuid4().hex}"
    known_ids = {str(target["id"]) for target in _targets(api_url)}

    warm_ui_route(_HOSTING_ROUTE)
    with open_settings_subroute(_HOSTING_ROUTE, timeout_ms=90_000) as (client, page):
        _open_hosting_page(client, page, hosting_url)

        providers = wait_for_state(client, page, _PROVIDERS_JS, timeout_sec=90.0, page_url=hosting_url)
        assert providers["labels"] == ["Vercel", "HTTP Webhook"], providers
        assert not any(name in str(providers["text"]) for name in ("Netlify", "Cloudflare")), providers

        added = client.evaluate(page, _ADD_WEBHOOK_TARGET_JS, timeout_sec=15.0)
        assert isinstance(added, dict) and added.get("ok") is True, added
        card = wait_for_state(client, page, _WEBHOOK_CARD_JS, timeout_sec=60.0, page_url=hosting_url)
        target_id = str(card["id"])
        created = [t for t in _targets(api_url) if str(t["id"]) not in known_ids]
        assert [(t["id"], t["provider_type"]) for t in created] == [(target_id, "http_webhook")], created

        saved = client.evaluate(page, _fill_and_save_js(target_id, secret), timeout_sec=30.0)
        assert isinstance(saved, dict) and saved.get("ok") is True, saved
        _wait_for(
            lambda: _credentials(api_url, target_id).get("configured") is True,
            "pressing Save target never stored the credentials",
        )
        listed = http_json("GET", f"{api_url}{_TARGETS_PATH}")
        stored = next(t for t in _targets(api_url) if str(t["id"]) == target_id)
        config = stored["config"]
        assert isinstance(config, dict) and config.get("webhook_url") == _WEBHOOK_URL, stored
        assert secret not in json.dumps(listed), "the secret is echoed by the target list"
        assert secret not in json.dumps(_credentials(api_url, target_id)), "the secret is echoed by the credentials status"

        _open_hosting_page(client, page, hosting_url)
        fields = wait_for_state(client, page, _field_values_js(target_id), timeout_sec=60.0, page_url=hosting_url)
        assert fields["url"] == _WEBHOOK_URL, fields
        assert fields["secret"] == "", "the page shows the stored secret after a reload"

        deleted = client.evaluate(page, _delete_target_js(target_id), timeout_sec=15.0)
        assert isinstance(deleted, dict) and deleted.get("ok") is True, deleted
        wait_for_state(client, page, _card_gone_js(target_id), timeout_sec=60.0, page_url=hosting_url)

    assert target_id not in {str(t["id"]) for t in _targets(api_url)}
    assert _credentials(api_url, target_id).get("configured") is not True, "deleting the target left its credentials behind"
