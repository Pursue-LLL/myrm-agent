"""Real Chrome MCP E2E: the media cards of a generated turn load their files, also after a reload.

[INPUT]
- app.api.chats.test_fixtures.media_cards (POS: seeds a chat whose assistant reply registered one generated media)
- tests.support.chrome_mcp_e2e (POS: real Chrome page access, E2E bridge waits and reloads)

[OUTPUT]
Fails when a card of an image task, a video task, a synchronous image edit or speech shows a media element that did
not load (``<img>`` complete with a width, ``<video>`` and ``<audio>`` past their metadata), beside a reply that also
carries words or after a reload. Two controls keep that check honest: a task result no browser can load must not pass
it, and a task card whose record is gone must settle on its expired notice instead of staying a skeleton.

[POS]
The check the other media E2E tests never made: they assert the panel's text, so a card with a broken image passed.
Safari has no automation channel here; it is checked by hand with a throwaway page opened through ``open -a Safari``
that posts the same element states (and a seek on a 26 MB video) back to a local server.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_REPLY_TEXT = "MYRM_E2E_MEDIA_CARD_REPLY"
_EXPIRED_NOTICE = "task record has expired|任务记录已过期|任務記錄已過期"
_UNLOADABLE_WAIT_SEC = 25.0

_DISMISS_MIGRATION_JS = """(() => {
  try {
    localStorage.setItem('myrm.proactive.dismissed.migration-discovery', 'forever');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_BRIDGE_ATTACH_READY_JS = """(() => ({
  ready: typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function',
}))()"""


def _attach_chat_probe(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {{
    return {{ ok: false, err: 'no-bridge' }};
  }}
  await bridge.attachToChat({chat_id_json});
  const snap = bridge.turnSnapshot?.() ?? {{}};
  return {{ ok: snap.chatId === {chat_id_json}, snap }};
}})()"""


def _chat_shell_ready_js(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(() => {{
  const state = window.__MYRM_E2E_CHAT__?.getChatShellState?.() ?? {{}};
  return {{
    ready:
      state.chatId === {chat_id_json}
      && state.isMessagesLoaded === true
      && state.notFound !== true
      && state.loadError !== true,
    state,
  }};
}})()"""


def _media_probe_js(kind: str, marker: str) -> str:
    """Whether the media element carrying ``marker`` in its address has loaded, and whether the reply text is shown."""
    return f"""(() => {{
  const marker = {json.dumps(marker)};
  const carries = (element) => (element.currentSrc || element.src || '').includes(marker);
  const images = Array.from(document.images).filter(carries);
  const videos = Array.from(document.querySelectorAll('video')).filter(carries);
  const audios = Array.from(document.querySelectorAll('audio')).filter(carries);
  const loaded = {{
    image: images.length > 0 && images.every((img) => img.complete && img.naturalWidth > 0),
    video: videos.length > 0 && videos.every((video) => video.readyState >= 1 && video.duration > 0),
    tts: audios.length > 0 && audios.every((audio) => audio.readyState >= 1),
  }}[{json.dumps(kind)}] === true;
  return {{
    ready: loaded,
    replyVisible: (document.body?.innerText || '').includes({json.dumps(_REPLY_TEXT)}),
    images: images.map((img) => ({{ complete: img.complete, width: img.naturalWidth }})),
    videos: videos.map((video) => ({{ readyState: video.readyState, duration: video.duration }})),
    audios: audios.map((audio) => ({{ readyState: audio.readyState }})),
  }};
}})()"""


def _reply_visible_js() -> str:
    return f"""(() => ({{
  ready: (document.body?.innerText || '').includes({json.dumps(_REPLY_TEXT)}),
}}))()"""


def _expired_notice_js() -> str:
    return f"""(() => {{
  const text = document.body?.innerText || '';
  return {{
    ready: new RegExp({json.dumps(_EXPIRED_NOTICE)}).test(text),
    mediaElements: document.querySelectorAll('video, audio').length,
  }};
}})()"""


def _seed(kind: str, address: str | None = None) -> dict[str, object]:
    query = f"kind={kind}" + (f"&address={address}" if address else "")
    seeded = http_json("POST", f"{get_e2e_api_url()}/api/v1/chats/test/seed-media-cards-fixture?{query}")
    assert isinstance(seeded, dict)
    assert str(seeded.get("chat_id") or "").startswith("e2emedia")
    return seeded


def _attach_and_wait_for_messages(client: ChromeMcpClient, page: McpPage, chat_url: str, chat_id: str) -> None:
    wait_for_state(client, page, _BRIDGE_ATTACH_READY_JS, timeout_sec=120.0, page_url=chat_url)
    client.evaluate(page, _attach_chat_probe(chat_id), timeout_sec=90.0)
    shell = wait_for_state(client, page, _chat_shell_ready_js(chat_id), timeout_sec=120.0, page_url=chat_url)
    assert shell.get("ready") is True, shell


@contextmanager
def _seeded_chat(kind: str, address: str | None = None) -> Iterator[tuple[ChromeMcpClient, McpPage, dict[str, object], str]]:
    """A page on the chat the fixture seeded, hydrated; yields the client, the page, the seed and the chat URL."""
    prepare_e2e_ui_session(get_e2e_api_url())
    seeded = _seed(kind, address)
    chat_id = str(seeded["chat_id"])
    chat_url = f"{get_e2e_ui_url()}/{chat_id}"
    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        ensure_desktop_viewport(client, page)
        _attach_and_wait_for_messages(client, page, chat_url, chat_id)
        yield client, page, seeded, chat_url


def _reload(client: ChromeMcpClient, page: McpPage, seeded: dict[str, object], chat_url: str) -> None:
    reload_mcp_page(client, page, timeout_ms=60_000, target_url=chat_url)
    dismiss_blocking_modals(client, page, recover_url=chat_url)
    client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
    _attach_and_wait_for_messages(client, page, chat_url, str(seeded["chat_id"]))


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
@pytest.mark.parametrize("kind", ["image", "video", "image_edit", "tts"])
def test_generated_media_loads_beside_the_reply_and_after_a_reload(kind: str) -> None:
    with _seeded_chat(kind) as (client, page, seeded, chat_url):
        probe = _media_probe_js(kind if kind != "image_edit" else "image", str(seeded["marker"]))

        first = wait_for_state(client, page, probe, timeout_sec=90.0, page_url=chat_url)
        assert first.get("ready") is True, first
        assert first.get("replyVisible") is True, first

        _reload(client, page, seeded, chat_url)

        reloaded = wait_for_state(client, page, probe, timeout_sec=90.0, page_url=chat_url)
        assert reloaded.get("ready") is True, reloaded
        assert reloaded.get("replyVisible") is True, reloaded


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(240)
@pytest.mark.parametrize("kind", ["image", "video"])
def test_a_task_result_no_browser_can_load_never_passes_the_load_check(kind: str) -> None:
    """Negative control: the same probe that passes real files must stay red for an address that cannot load."""
    with _seeded_chat(kind, "file") as (client, page, seeded, chat_url):
        shown = wait_for_state(client, page, _reply_visible_js(), timeout_sec=60.0, page_url=chat_url)
        assert shown.get("ready") is True, shown

        # A wait that never sees the state turn ready gives up with the last state it read: the probe's "not loaded" verdict.
        with pytest.raises(AssertionError, match=r"did not become ready: \{'ready': False"):
            wait_for_state(
                client,
                page,
                _media_probe_js(kind, str(seeded["marker"])),
                timeout_sec=_UNLOADABLE_WAIT_SEC,
                page_url=chat_url,
            )


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(240)
@pytest.mark.parametrize("kind", ["image", "video"])
def test_a_task_card_whose_record_is_gone_settles_on_the_expired_notice(kind: str) -> None:
    with _seeded_chat(kind, "expired") as (client, page, _seeded, chat_url):
        expired = wait_for_state(client, page, _expired_notice_js(), timeout_sec=60.0, page_url=chat_url)
        assert expired.get("ready") is True, expired
        assert expired.get("mediaElements") == 0, expired
