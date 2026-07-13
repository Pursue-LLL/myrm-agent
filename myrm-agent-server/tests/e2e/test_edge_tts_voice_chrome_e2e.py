"""Chrome E2E: Edge TTS GPL isolation + Voice Settings UX (CDP, not Playwright).

Prerequisites:
  bash myrm-agent/scripts/dev/chrome-e2e-preflight.sh  # CHROME_E2E_READY
  No parallel pytest during UI (wave lease recommended).

Covers:
  - Voice Settings: no amber banner when edge_tts_available=true
  - Live TTS API success with default channel ttsMode=off (Web read-aloud path)
  - Read-aloud browser fetch to synthesize-stream (webTtsProvider=edge)
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request

import pytest

BASE_URL = "http://127.0.0.1:3000"
API_URL = "http://127.0.0.1:8080"
CHROME_CDP_LIST = "http://127.0.0.1:9333/json/list"
VOICE_SETTINGS_URL = f"{BASE_URL}/settings/channels?sub=voice"


def _http_json(method: str, url: str, body: dict[str, object] | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


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
    info = _http_json("GET", f"{API_URL}/api/v1/health/info")
    return isinstance(info, dict) and info.get("edge_tts_available") is True


def _open_page_ws(target_url: str) -> str | None:
    new_url = CHROME_CDP_LIST.replace("/json/list", "/json/new")
    req = urllib.request.Request(f"{new_url}?{target_url}", method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            page = json.loads(resp.read())
    except urllib.error.URLError:
        return None
    ws = page.get("webSocketDebuggerUrl")
    return str(ws) if isinstance(ws, str) else None


def _find_page_ws(target_url: str) -> str | None:
    try:
        with urllib.request.urlopen(CHROME_CDP_LIST, timeout=5) as resp:
            pages = json.loads(resp.read())
    except Exception:
        return None
    for page in pages:
        if page.get("type") != "page":
            continue
        url = page.get("url", "")
        if target_url.rstrip("/") in url or url.rstrip("/") == target_url.rstrip("/"):
            ws = page.get("webSocketDebuggerUrl")
            if isinstance(ws, str):
                return ws
    return _open_page_ws(target_url)


@pytest.fixture(scope="module")
def chrome_preflight() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:9333/json/version", timeout=3):
            pass
    except Exception as exc:
        pytest.skip(f"Chrome E2E not ready — run chrome-e2e-preflight.sh: {exc}")


@pytest.fixture
def chrome_ws(chrome_preflight: None) -> str:
    ws_url = _open_page_ws(BASE_URL + "/") or _find_page_ws(BASE_URL + "/")
    if not ws_url:
        pytest.skip("Chrome E2E tab unavailable on port 9333")
    return ws_url


@pytest.fixture
def voice_chrome_ws(chrome_preflight: None) -> str:
    ws_url = _find_page_ws(VOICE_SETTINGS_URL) or _open_page_ws(VOICE_SETTINGS_URL)
    if not ws_url:
        pytest.skip("Chrome E2E voice tab unavailable on port 9333")
    return ws_url


class _CdpSession:
    def __init__(self, ws_url: str) -> None:
        self._ws_url = ws_url
        self._mid = 0

    async def __aenter__(self) -> _CdpSession:
        import websockets

        self._ws = await websockets.connect(self._ws_url, max_size=10**7, open_timeout=10).__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._ws.__aexit__(*args)

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
            if "exceptionDetails" in result:
                raise AssertionError(f"CDP eval failed: {result['exceptionDetails']}")
            payload = result.get("result", {}).get("result", {})
            return payload.get("value", payload.get("description"))

    async def dismiss_migration(self) -> None:
        await self.eval(
            """(() => {
              sessionStorage.setItem('migration_discovery_dismissed', 'true');
              sessionStorage.setItem('competitor_migration_dismissed', 'true');
              return { ok: true };
            })()""",
            await_promise=False,
        )

    async def wait_voice_settings(self) -> dict[str, object]:
        ready: dict[str, object] = {}
        for _ in range(45):
            ready = await self.eval(
                """(() => {
                  const text = document.body.innerText || '';
                  const skeletons = document.querySelectorAll('[class*="skeleton" i]').length;
                  const hasVoiceHeading = /语音|Voice|Text-to-Speech|Edge TTS/i.test(text);
                  const onVoiceRoute = location.search.includes('sub=voice');
                  const voiceTab = Array.from(document.querySelectorAll('[role="tab"]'))
                    .find((el) => /语音|Voice/i.test(el.textContent || ''));
                  if (onVoiceRoute && voiceTab && voiceTab.getAttribute('aria-selected') !== 'true') {
                    voiceTab.click();
                  }
                  return {
                    url: location.href,
                    hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
                    skeletons,
                    hasVoiceHeading,
                    onVoiceRoute,
                    showBanner: /Edge TTS is not available|Edge TTS 不可用/i.test(text),
                    readyState: document.readyState,
                  };
                })()""",
                await_promise=False,
            )
            if (
                isinstance(ready, dict)
                and ready.get("hasLayout")
                and ready.get("onVoiceRoute")
                and int(ready.get("skeletons", 99)) < 4
                and ready.get("hasVoiceHeading")
            ):
                return ready
            await asyncio.sleep(1)
        raise AssertionError(f"Voice settings page not ready: {ready}")


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_voice_settings_no_edge_banner_when_available(voice_chrome_ws: str) -> None:
    if not _edge_tts_available():
        pytest.skip("edge_tts_available=false — banner covered by TestClient 503")

    _ensure_voice_feature_enabled()

    async with _CdpSession(voice_chrome_ws) as cdp:
        await cdp.dismiss_migration()
        page = await cdp.wait_voice_settings()

    assert page.get("showBanner") is False, page
    assert "sub=voice" in str(page.get("url", ""))


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_live_tts_synthesize_after_voice_config() -> None:
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
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_read_aloud_edge_stream_from_browser_context(chrome_ws: str) -> None:
    """Browser context fetch to synthesize-stream (same path as useTTS ReadAloud)."""
    if not _edge_tts_available():
        pytest.skip("edge_tts_available=false")

    _seed_voice_and_personal_settings()
    import websockets

    async with websockets.connect(chrome_ws, max_size=10**7, open_timeout=10) as ws:
        mid = 0

        async def ev(expr: str, *, await_promise: bool = True) -> object:
            nonlocal mid
            mid += 1
            await ws.send(
                json.dumps(
                    {
                        "id": mid,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": expr,
                            "returnByValue": True,
                            "awaitPromise": await_promise,
                        },
                    }
                )
            )
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                result = json.loads(raw)
                if result.get("id") != mid:
                    continue
                if "exceptionDetails" in result:
                    raise AssertionError(f"CDP eval failed: {result['exceptionDetails']}")
                payload = result.get("result", {}).get("result", {})
                return payload.get("value")

        await ev(
            f"window.location.href = {json.dumps(BASE_URL + '/')}; 'nav'",
            await_promise=False,
        )
        await asyncio.sleep(2)

        result = await ev(
            """(async () => {
              const resp = await fetch('/api/v1/tts/synthesize-stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: 'edge read aloud e2e', provider: 'edge' }),
              });
              const reader = resp.body?.getReader();
              let bytes = 0;
              if (reader) {
                const chunk = await reader.read();
                bytes = chunk.value?.byteLength || 0;
                reader.releaseLock();
              }
              return { status: resp.status, bytes };
            })()""",
        )
        assert isinstance(result, dict), result
        assert result.get("status") == 200, result
        assert int(result.get("bytes", 0)) > 0, result
