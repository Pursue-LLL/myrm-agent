"""Chrome E2E: Edge TTS GPL isolation + Voice Settings UX (CDP, not Playwright).

Prerequisites:
  ./myrm ready --chrome
  Wave READ lease recommended when parallel agents are active.

Covers:
  - Voice Settings: no amber banner when edge_tts_available=true
  - Live TTS API success with channel ttsMode=off (Web read-aloud path)
  - Read-aloud browser fetch to /tts/synthesize via :3000 proxy (webTtsProvider=edge)
  - Parallel isolated tabs: voice banner + read-aloud fetch concurrently
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

from dataclasses import dataclass

import pytest

BASE_URL = "http://127.0.0.1:3000"
API_URL = "http://127.0.0.1:8080"
CHROME_CDP_LIST = "http://127.0.0.1:9333/json/list"
VOICE_SETTINGS_URL = f"{BASE_URL}/settings/channels?sub=voice"

_DISMISS_MIGRATION_JS = """(() => {
  sessionStorage.setItem('migration_discovery_dismissed', 'true');
  sessionStorage.setItem('competitor_migration_dismissed', 'true');
  return { ok: true };
})()"""

_VOICE_PROBE_JS = """(() => {
  const text = document.body.innerText || '';
  const skeletons = document.querySelectorAll('[class*="skeleton" i]').length;
  const hasVoicePanel = !!document.querySelector('[data-testid="voice-settings-panel"]');
  const onVoiceRoute = location.search.includes('sub=voice')
    && location.pathname.includes('/settings/channels');
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const voiceTab = tabs.find((el) => /语音|Voice/i.test(el.textContent || ''))
    || (tabs.length >= 3 ? tabs[2] : null);
  if (onVoiceRoute && voiceTab && voiceTab.getAttribute('aria-selected') !== 'true') {
    voiceTab.click();
  }
  return {
    url: location.href,
    hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
    skeletons,
    hasVoicePanel,
    onVoiceRoute,
    tabCount: tabs.length,
    showBanner: /Edge TTS is not available|Edge TTS 不可用/i.test(text),
    readyState: document.readyState,
  };
})()"""

_LAYOUT_PROBE_JS = """(() => ({
  hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
  url: location.href,
  readyState: document.readyState,
}))()"""


def _http_json(method: str, url: str, body: dict[str, object] | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def _server_reachable() -> bool:
    try:
        with urllib.request.urlopen(f"{API_URL}/api/v1/health/info", timeout=5):
            return True
    except Exception:
        return False


def _require_live_stack() -> None:
    if not _server_reachable():
        pytest.skip("Live server :8080 not reachable — run ./myrm ready")


def _ensure_voice_feature_enabled() -> None:
    _http_json(
        "POST",
        f"{API_URL}/api/v1/features/voice_interaction/toggle",
        {"enabled": True},
    )


def _put_edge_voice_config() -> None:
    _http_json(
        "PUT",
        f"{API_URL}/api/v1/config/voice",
        {
            "deviceId": "web",
            "value": {
                "sttEnabled": False,
                "ttsMode": "off",
                "ttsProvider": "edge",
                "ttsVoice": "",
                "ttsSpeed": 1.0,
                "ttsPitch": 0,
                "sttProvider": "openai",
                "sttApiKey": "",
                "sttModel": "whisper-1",
                "sttLanguage": "",
                "sttLocalModel": "base",
                "sttLocalDevice": "auto",
                "sttLocalComputeType": "auto",
                "sttBaseUrl": "",
                "ttsApiKey": "",
                "ttsBaseUrl": "",
                "ttsMaxLength": 4000,
                "ttsSummaryEnabled": True,
                "ttsSummaryThreshold": 1500,
                "ttsSummaryModel": "",
                "geminiLiveModel": "gemini-2.5-flash-preview-native-audio-dialog",
            },
        },
    )


def _seed_voice_and_personal_settings() -> None:
    _ensure_voice_feature_enabled()
    _put_edge_voice_config()
    personal = _http_json("GET", f"{API_URL}/api/v1/config/personalSettings")
    assert isinstance(personal, dict)
    value = personal.get("value")
    if not isinstance(value, dict):
        value = {}
    value = {**value, "webTtsProvider": "edge"}
    _http_json(
        "PUT",
        f"{API_URL}/api/v1/config/personalSettings",
        {"deviceId": "web", "value": value},
    )


def _edge_tts_available() -> bool:
    try:
        info = _http_json("GET", f"{API_URL}/api/v1/health/info")
    except Exception:
        return False
    return isinstance(info, dict) and info.get("edge_tts_available") is True


def _assert_cdp_write_allowed(operation: str) -> None:
    dev_lib = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
    if str(dev_lib) not in sys.path:
        sys.path.insert(0, str(dev_lib))
    from cdp_write_guard import assert_cdp_write_allowed

    assert_cdp_write_allowed(operation=operation)


def _parse_eval_value(result: dict[str, object]) -> object:
    if "exceptionDetails" in result:
        raise AssertionError(f"CDP eval failed: {result['exceptionDetails']}")
    payload = result.get("result", {})
    if not isinstance(payload, dict):
        raise AssertionError(f"CDP eval missing result payload: {result}")
    inner = payload.get("result", {})
    if not isinstance(inner, dict):
        raise AssertionError(f"CDP eval missing inner result: {result}")
    if "value" in inner:
        return inner["value"]
    if inner.get("type") == "undefined":
        return None
    description = inner.get("description")
    if description is not None:
        return description
    raise AssertionError(f"CDP eval returned unparseable value: {result}")


@dataclass(frozen=True)
class _CdpPage:
    ws_url: str
    target_id: str


def _close_page_target(target_id: str) -> None:
    if not target_id:
        return
    close_url = CHROME_CDP_LIST.replace("/json/list", f"/json/close/{target_id}")
    req = urllib.request.Request(close_url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except urllib.error.URLError:
        pass


def _open_page(target_url: str) -> _CdpPage | None:
    """Open a fresh isolated Chrome tab (parallel-safe — one owner per test)."""
    _assert_cdp_write_allowed(operation="json/new")
    new_url = CHROME_CDP_LIST.replace("/json/list", "/json/new")
    encoded = quote(target_url, safe="")
    req = urllib.request.Request(f"{new_url}?{encoded}", method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            page = json.loads(resp.read())
    except urllib.error.URLError:
        return None
    ws = page.get("webSocketDebuggerUrl")
    target_id = page.get("id")
    if not isinstance(ws, str) or not isinstance(target_id, str):
        return None
    return _CdpPage(ws_url=ws, target_id=target_id)


@pytest.fixture(scope="module")
def chrome_preflight() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:9333/json/version", timeout=3):
            pass
    except Exception as exc:
        pytest.skip(f"Chrome E2E not ready — run ./myrm ready --chrome: {exc}")


@pytest.fixture
def chrome_page(chrome_preflight: None):
    page = _open_page(f"{BASE_URL}/")
    if page is None:
        pytest.skip("Chrome E2E tab unavailable on port 9333")
    yield page.ws_url
    _close_page_target(page.target_id)


@pytest.fixture
def voice_chrome_page(chrome_preflight: None):
    page = _open_page(f"{BASE_URL}/")
    if page is None:
        pytest.skip("Chrome E2E tab unavailable on port 9333")
    yield page.ws_url
    _close_page_target(page.target_id)


class _CdpSession:
    def __init__(self, ws_url: str) -> None:
        self._ws_url = ws_url
        self._mid = 0

    async def __aenter__(self) -> _CdpSession:
        import websockets

        self._ws = await websockets.connect(self._ws_url, max_size=10**7, open_timeout=10).__aenter__()
        await self._call("Runtime.enable")
        await self._call("Page.enable")
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._ws.__aexit__(*args)

    async def _call(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self._mid += 1
        await self._ws.send(
            json.dumps({"id": self._mid, "method": method, "params": params or {}}),
        )
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=30)
            result = json.loads(raw)
            if result.get("id") != self._mid:
                continue
            payload = result.get("result")
            return payload if isinstance(payload, dict) else {}

    async def eval(self, expression: str, *, await_promise: bool = True) -> object:
        self._mid += 1
        await self._ws.send(
            json.dumps(
                {
                    "id": self._mid,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": True,
                        "awaitPromise": await_promise,
                    },
                }
            )
        )
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=120)
            result = json.loads(raw)
            if result.get("id") != self._mid:
                continue
            return _parse_eval_value(result)

    async def navigate(self, url: str) -> None:
        await self._call("Page.navigate", {"url": url})
        await asyncio.sleep(2)

    async def dismiss_migration(self) -> None:
        await self.eval(_DISMISS_MIGRATION_JS, await_promise=False)

    async def wait_app_layout(self, *, timeout_sec: float = 90.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        reloaded = False
        while time.monotonic() < deadline:
            state = await self.eval(_LAYOUT_PROBE_JS, await_promise=False)
            last = state if isinstance(state, dict) else {"probeError": state}
            if last.get("hasLayout") and last.get("readyState") in ("complete", "interactive"):
                return last
            if (
                not reloaded
                and not last.get("hasLayout")
                and last.get("readyState") in ("complete", "interactive")
            ):
                reloaded = True
                await self.eval("location.reload(); 'reload'", await_promise=False)
                await asyncio.sleep(3)
                continue
            await asyncio.sleep(1)
        raise AssertionError(f"App layout not ready within {timeout_sec:.0f}s: {last}")

    async def wait_voice_settings(self) -> dict[str, object]:
        await self.dismiss_migration()
        await self.navigate(f"{BASE_URL}/")
        await self.wait_app_layout()
        await self.navigate(VOICE_SETTINGS_URL)
        ready: dict[str, object] = {}
        for _ in range(45):
            state = await self.eval(_VOICE_PROBE_JS, await_promise=False)
            ready = state if isinstance(state, dict) else {"probeError": state}
            if (
                ready.get("hasLayout")
                and ready.get("onVoiceRoute")
                and ready.get("readyState") in ("complete", "interactive")
                and int(ready.get("skeletons", 99)) < 4
                and ready.get("hasVoicePanel")
            ):
                return ready
            await asyncio.sleep(1)
        raise AssertionError(f"Voice settings page not ready: {ready}")


async def _probe_voice_banner(ws_url: str) -> dict[str, object]:
    async with _CdpSession(ws_url) as cdp:
        return await cdp.wait_voice_settings()


async def _probe_read_aloud_fetch(ws_url: str) -> dict[str, object]:
    async with _CdpSession(ws_url) as cdp:
        await cdp.dismiss_migration()
        await cdp.navigate(f"{BASE_URL}/")
        await cdp.wait_app_layout()
        result = await cdp.eval(
            f"""(async () => {{
              try {{
                await fetch({json.dumps(BASE_URL + "/api/v1/features/voice_interaction/toggle")}, {{
                  method: 'POST',
                  headers: {{ 'Content-Type': 'application/json' }},
                  body: JSON.stringify({{ enabled: true }}),
                }});
                const resp = await fetch({json.dumps(BASE_URL + "/api/v1/tts/synthesize")}, {{
                  method: 'POST',
                  headers: {{ 'Content-Type': 'application/json' }},
                  body: JSON.stringify({{ text: 'edge parallel read aloud', provider: 'edge' }}),
                }});
                const blob = await resp.blob();
                return {{ status: resp.status, bytes: blob.size, tab: 'read-aloud' }};
              }} catch (err) {{
                return {{ status: null, bytes: 0, error: String(err), tab: 'read-aloud' }};
              }}
            }})()""",
        )
    if not isinstance(result, dict):
        raise AssertionError(f"Read-aloud probe returned non-dict: {result}")
    return result


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(300)
@pytest.mark.asyncio
async def test_voice_settings_no_edge_banner_when_available(voice_chrome_page: str) -> None:
    _require_live_stack()
    if not _edge_tts_available():
        pytest.skip("edge_tts_available=false — banner covered by TestClient 503")

    _ensure_voice_feature_enabled()

    async with _CdpSession(voice_chrome_page) as cdp:
        page = await cdp.wait_voice_settings()

    assert page.get("hasVoicePanel") is True, page
    assert page.get("showBanner") is False, page
    assert "sub=voice" in str(page.get("url", ""))


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_live_tts_synthesize_after_voice_config() -> None:
    _require_live_stack()
    if not _edge_tts_available():
        pytest.skip("edge_tts_available=false")

    _ensure_voice_feature_enabled()
    _put_edge_voice_config()
    req = urllib.request.Request(
        f"{API_URL}/api/v1/tts/synthesize",
        data=json.dumps({"text": "edge tts chrome e2e"}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        assert resp.status == 200
        body = resp.read(16)
    assert body[:3] == b"ID3" or (body[0] == 0xFF and (body[1] & 0xE0) == 0xE0)


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(300)
@pytest.mark.asyncio
async def test_read_aloud_edge_api_from_browser_context(chrome_page: str) -> None:
    """Browser same-origin fetch to /tts/synthesize (ReadAloud API path via Next proxy)."""
    _require_live_stack()
    if not _edge_tts_available():
        pytest.skip("edge_tts_available=false")

    _seed_voice_and_personal_settings()

    async with _CdpSession(chrome_page) as cdp:
        await cdp.dismiss_migration()
        await cdp.navigate(f"{BASE_URL}/")
        await cdp.wait_app_layout()

        result = await cdp.eval(
            f"""(async () => {{
              try {{
                await fetch({json.dumps(BASE_URL + "/api/v1/features/voice_interaction/toggle")}, {{
                  method: 'POST',
                  headers: {{ 'Content-Type': 'application/json' }},
                  body: JSON.stringify({{ enabled: true }}),
                }});
                const resp = await fetch({json.dumps(BASE_URL + "/api/v1/tts/synthesize")}, {{
                  method: 'POST',
                  headers: {{ 'Content-Type': 'application/json' }},
                  body: JSON.stringify({{ text: 'edge read aloud e2e', provider: 'edge' }}),
                }});
                const blob = await resp.blob();
                return {{ status: resp.status, bytes: blob.size }};
              }} catch (err) {{
                return {{ status: null, bytes: 0, error: String(err) }};
              }}
            }})()""",
        )

    assert isinstance(result, dict), result
    assert result.get("error") is None, result
    assert result.get("status") == 200, result
    assert int(result.get("bytes", 0)) > 0, result


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(420)
@pytest.mark.asyncio
async def test_edge_tts_parallel_tabs_isolated(chrome_preflight: None) -> None:
    """Parallel lanes: voice banner (tab A) + read-aloud fetch (tab B) + no shared CDP session."""
    _require_live_stack()
    if not _edge_tts_available():
        pytest.skip("edge_tts_available=false")

    _seed_voice_and_personal_settings()
    _ensure_voice_feature_enabled()

    voice_tab = _open_page(f"{BASE_URL}/")
    read_tab = _open_page(f"{BASE_URL}/")
    if voice_tab is None or read_tab is None:
        pytest.skip("Chrome E2E tabs unavailable on port 9333")

    try:
        voice_result, read_result = await asyncio.gather(
            _probe_voice_banner(voice_tab.ws_url),
            _probe_read_aloud_fetch(read_tab.ws_url),
        )
    finally:
        _close_page_target(voice_tab.target_id)
        _close_page_target(read_tab.target_id)

    assert voice_result.get("hasVoicePanel") is True, voice_result
    assert voice_result.get("showBanner") is False, voice_result
    assert read_result.get("error") is None, read_result
    assert read_result.get("status") == 200, read_result
    assert int(read_result.get("bytes", 0)) > 0, read_result
