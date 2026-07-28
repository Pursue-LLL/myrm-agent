"""Chrome E2E: Edge TTS GPL isolation + Voice Settings UX through MCP mux.

Prerequisites:
  ./myrm ready --chrome
  Wave READ lease recommended when parallel agents are active.
  Run one test at a time: path::test_name (whole-file batch denied by E2E_FILE_BATCH_DENIED).
  Chrome UI tests also need: ./myrm test -m chrome_e2e path::test_name

Covers:
  - Voice Settings: no amber banner when edge_tts_available=true
  - Voice Settings: no local STT banner when local_stt_available=true and provider=local
  - Live health/info local_stt_available + GET /stt/status
  - Live TTS API success with channel ttsMode=off (Web read-aloud path)
  - Read-aloud browser fetch to /tts/synthesize via :3000 proxy (webTtsProvider=edge)
  - Parallel isolated tabs: voice banner + read-aloud fetch concurrently
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from pytest import FixtureRequest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import get_e2e_api_url, get_e2e_ui_url  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from tests.support.chrome_mcp_e2e import open_mcp_page, wait_for_state, warm_ui_route  # noqa: E402
from tests.support.e2e_runtime_guard import heartbeat_e2e_lease  # noqa: E402
from tests.support.e2e_wall_progress import touch_e2e_wall_progress, write_e2e_session_snapshot  # noqa: E402


def _voice_settings_url() -> str:
    return f"{get_e2e_ui_url()}/settings/channels?sub=voice"


_DISMISS_MIGRATION_JS = """(() => {
  sessionStorage.setItem('migration_discovery_dismissed', 'true');
  sessionStorage.setItem('competitor_migration_dismissed', 'true');
  return { ok: true };
})()"""

_VOICE_PROBE_JS = """(() => {
  try {
    window.resizeTo(1280, 900);
  } catch {
    // ignore
  }
  const body = document.body;
  const text = body ? (body.innerText || '') : '';
  const skeletons = document.querySelectorAll('[class*="skeleton" i], .animate-pulse').length;
  const hasVoicePanel = !!document.querySelector('[data-testid="voice-settings-panel"]');
  const onChannelsSettings = location.pathname.includes('/settings/channels');
  const onVoiceRoute = location.search.includes('sub=voice') && onChannelsSettings;
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const voiceTab = tabs.find((el) => /语音|Voice/i.test(el.textContent || ''))
    || (tabs.length >= 3 ? tabs[2] : null);
  if (onChannelsSettings && !hasVoicePanel && voiceTab && voiceTab.getAttribute('aria-selected') !== 'true') {
    voiceTab.click();
  }
  if (onChannelsSettings && !hasVoicePanel && tabs.length === 0) {
    const menuButtons = Array.from(document.querySelectorAll('aside button, nav button'));
    const channelsBtn = menuButtons.find((el) =>
      /Channels|消息通道|渠道/i.test(el.textContent || '')
    );
    if (channelsBtn) {
      channelsBtn.click();
    }
  }
  return {
    url: location.href,
    hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
    skeletons,
    hasVoicePanel,
    onVoiceRoute,
    onChannelsSettings,
    tabCount: tabs.length,
    showEdgeBanner: /Edge TTS is not available|Edge TTS 不可用/i.test(text),
    showLocalSttBanner: /Local Whisper STT is not available|本地 Whisper 语音识别不可用/i.test(text),
    showLocalSttHint: /Free, no API key required|无需 API Key|Audio stays on your device|音频保留在/i.test(text),
    readyState: document.readyState,
    viewportWidth: window.innerWidth,
    ready: !!(
      document.querySelector('[data-testid="app-layout"]')
      && hasVoicePanel
      && skeletons < 6
      && onChannelsSettings
      && (document.readyState === 'complete' || document.readyState === 'interactive')
    ),
  };
})()"""

_LAYOUT_PROBE_JS = """(() => ({
  hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
  url: location.href,
  readyState: document.readyState,
}))()"""


def _http_json(method: str, url: str, body: dict[str, object] | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method
    )  # noqa: S310 - loopback only
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - loopback only
        raw = resp.read()
        return json.loads(raw) if raw else {}


def _server_reachable() -> bool:
    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed loopback URL
            f"{get_e2e_api_url()}/api/v1/health/info",
            timeout=5,
        ):
            return True
    except Exception:
        return False


def _require_live_stack() -> None:
    deadline = time.monotonic() + 120.0
    while time.monotonic() < deadline:
        if _server_reachable():
            return
        time.sleep(2.0)
    pytest.fail(
        "Live E2E API not reachable — run via ./myrm test -m e2e after ./myrm ready --chrome"
    )


def _ensure_voice_feature_enabled() -> None:
    _http_json(
        "POST",
        f"{get_e2e_api_url()}/api/v1/features/voice_interaction/toggle",
        {"enabled": True},
    )


def _put_local_voice_config() -> None:
    _http_json(
        "PUT",
        f"{get_e2e_api_url()}/api/v1/config/voice",
        {
            "deviceId": "web",
            "value": {
                "sttEnabled": True,
                "ttsMode": "off",
                "ttsProvider": "edge",
                "ttsVoice": "",
                "ttsSpeed": 1.0,
                "ttsPitch": 0,
                "sttProvider": "local",
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


def _put_edge_voice_config() -> None:
    _http_json(
        "PUT",
        f"{get_e2e_api_url()}/api/v1/config/voice",
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
    personal = _http_json("GET", f"{get_e2e_api_url()}/api/v1/config/personalSettings")
    assert isinstance(personal, dict)
    value = personal.get("value")
    if not isinstance(value, dict):
        value = {}
    value = {**value, "webTtsProvider": "edge"}
    _http_json(
        "PUT",
        f"{get_e2e_api_url()}/api/v1/config/personalSettings",
        {"deviceId": "web", "value": value},
    )


def _local_stt_available() -> bool:
    try:
        info = _http_json("GET", f"{get_e2e_api_url()}/api/v1/health/info")
    except Exception:
        return False
    return isinstance(info, dict) and info.get("local_stt_available") is True


def _edge_tts_available() -> bool:
    try:
        info = _http_json("GET", f"{get_e2e_api_url()}/api/v1/health/info")
    except Exception:
        return False
    return isinstance(info, dict) and info.get("edge_tts_available") is True


def _feature_override_snapshot() -> tuple[bool, bool]:
    payload = _http_json("GET", f"{get_e2e_api_url()}/api/v1/features")
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise AssertionError(f"Invalid feature status payload: {payload!r}")
    for item in payload["features"]:
        if isinstance(item, dict) and item.get("id") == "voice_interaction":
            return bool(item.get("enabled")), bool(item.get("is_overridden"))
    raise AssertionError("voice_interaction feature status missing")


def _config_value_snapshot(key: str) -> dict[str, object]:
    payload = _http_json("GET", f"{get_e2e_api_url()}/api/v1/config/{key}")
    if not isinstance(payload, dict) or not isinstance(payload.get("value"), dict):
        raise AssertionError(f"Invalid {key} config payload: {payload!r}")
    return payload["value"]


_CHROME_NEW_PAGE_TIMEOUT_MS = 120_000


@pytest.fixture
def require_edge_tts_available() -> None:
    """Skip before Chrome spin-up when SHPOIB private runtime lacks voice-tts extra."""
    _require_live_stack()
    if not _edge_tts_available():
        pytest.skip("edge_tts_available=false — covered by TestClient / unit tests")


@pytest.fixture
def require_local_stt_available() -> None:
    """Skip before Chrome spin-up when local-stt extra is not installed."""
    _require_live_stack()
    if not _local_stt_available():
        pytest.skip("local_stt_available=false — covered by TestClient 503")


@pytest.fixture(autouse=True)
def restore_global_voice_state(request: pytest.FixtureRequest) -> Iterator[None]:
    """Keep global voice/config writes from leaking into later UI E2E tests."""
    if request.node.get_closest_marker("chrome_e2e") is None:
        yield
        return
    if not _server_reachable():
        yield
        return
    try:
        feature_enabled, feature_overridden = _feature_override_snapshot()
        voice = _config_value_snapshot("voice")
        personal = _config_value_snapshot("personalSettings")
    except Exception:
        yield
        return
    try:
        yield
    finally:
        if not _server_reachable():
            return
        try:
            _http_json(
                "PUT",
                f"{get_e2e_api_url()}/api/v1/config/voice",
                {"deviceId": "web", "value": voice},
            )
            _http_json(
                "PUT",
                f"{get_e2e_api_url()}/api/v1/config/personalSettings",
                {"deviceId": "web", "value": personal},
            )
            if feature_overridden:
                _http_json(
                    "POST",
                    f"{get_e2e_api_url()}/api/v1/features/voice_interaction/toggle",
                    {"enabled": feature_enabled},
                )
            else:
                _http_json(
                    "POST",
                    f"{get_e2e_api_url()}/api/v1/features/voice_interaction/reset",
                )
        except BaseException:
            pass


@pytest.fixture
def chrome_page(
    _require_live_e2e_lease: None,
) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    client = ChromeMcpClient()
    client.start()
    try:
        page = client.new_page(
            f"{get_e2e_ui_url()}/", timeout_ms=_CHROME_NEW_PAGE_TIMEOUT_MS
        )
        yield client, page
    finally:
        client.close()


@pytest.fixture
def voice_chrome_page(
    _require_live_e2e_lease: None,
) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    client = ChromeMcpClient()
    client.start()
    try:
        page = client.new_page(
            f"{get_e2e_ui_url()}/", timeout_ms=_CHROME_NEW_PAGE_TIMEOUT_MS
        )
        yield client, page
    finally:
        client.close()


class _McpSession:
    def __init__(self, client: ChromeMcpClient, page: McpPage) -> None:
        self._client = client
        self._page = page

    async def __aenter__(self) -> _McpSession:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def eval(self, expression: str, *, await_promise: bool = True) -> object:
        del await_promise
        return await asyncio.to_thread(
            self._client.evaluate,
            self._page,
            expression,
            timeout_sec=120.0,
        )

    async def navigate(self, url: str) -> None:
        await asyncio.to_thread(
            self._client.navigate, self._page, url, timeout_ms=15_000
        )
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
            if last.get("hasLayout") and last.get("readyState") in (
                "complete",
                "interactive",
            ):
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
        voice_url = _voice_settings_url()
        warm_ui_route("/settings/channels?sub=voice", timeout_sec=90.0)
        await self.dismiss_migration()
        await self.navigate(voice_url)
        await self.wait_app_layout(timeout_sec=120.0)
        ready: dict[str, object] = {}
        for _ in range(90):
            try:
                state = await self.eval(_VOICE_PROBE_JS, await_promise=False)
            except RuntimeError as exc:
                if "innerText" in str(exc) or "null" in str(exc).lower():
                    await asyncio.sleep(1)
                    continue
                raise
            ready = state if isinstance(state, dict) else {"probeError": state}
            if (
                ready.get("ready") is True
                or (
                    ready.get("hasLayout")
                    and ready.get("readyState") in ("complete", "interactive")
                    and int(ready.get("skeletons", 99)) < 6
                    and ready.get("hasVoicePanel")
                )
            ):
                return ready
            if ready.get("onChannelsSettings") and not ready.get("hasVoicePanel"):
                await self.navigate(voice_url)
            await asyncio.sleep(1)
        raise AssertionError(f"Voice settings page not ready: {ready}")


async def _probe_voice_banner(
    client: ChromeMcpClient, page: McpPage
) -> dict[str, object]:
    async with _McpSession(client, page) as cdp:
        return await cdp.wait_voice_settings()


def _probe_voice_settings_sync(
    client: ChromeMcpClient, page: McpPage
) -> dict[str, object]:
    """Sync voice settings probe — matches voice_memory_acl open_mcp_page pattern."""
    heartbeat_e2e_lease()
    write_e2e_session_snapshot(current_node="voice_settings_dismiss_migration", phase="body")
    client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
    heartbeat_e2e_lease()
    write_e2e_session_snapshot(current_node="voice_settings_navigate", phase="body")
    client.navigate(page, _voice_settings_url(), timeout_ms=90_000)
    heartbeat_e2e_lease()
    write_e2e_session_snapshot(current_node="voice_settings_wait_panel", phase="body")
    return wait_for_state(client, page, _VOICE_PROBE_JS, timeout_sec=90.0)


@contextmanager
def _voice_e2e_progress_loop(*, current_node: str) -> Iterator[None]:
    """Keep lease + wall progress fresh while mux new_page may block (anti hung-reap)."""
    stop = threading.Event()

    def _loop() -> None:
        while not stop.wait(15.0):
            heartbeat_e2e_lease()
            touch_e2e_wall_progress(current_node=current_node)

    worker = threading.Thread(target=_loop, name="voice-e2e-progress", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=2.0)


def _chrome_probe_voice_settings_with_retry(*, progress_node: str) -> dict[str, object]:
    warm_ui_route("/settings/channels?sub=voice", timeout_sec=90.0)
    ui_base = get_e2e_ui_url()
    last_exc: BaseException | None = None
    for attempt in range(4):
        node = f"{progress_node}:open_mcp:{attempt}"
        with _voice_e2e_progress_loop(current_node=node):
            heartbeat_e2e_lease()
            touch_e2e_wall_progress(current_node=node)
            try:
                with open_mcp_page(ui_base, timeout_ms=60_000) as (client, page):
                    return _probe_voice_settings_sync(client, page)
            except BaseException as exc:
                last_exc = exc
                touch_e2e_wall_progress(current_node=f"{node}:retry")
                time.sleep(min(5 * (attempt + 1), 15))
    assert last_exc is not None
    raise last_exc


async def _probe_read_aloud_fetch(
    client: ChromeMcpClient,
    page: McpPage,
) -> dict[str, object]:
    async with _McpSession(client, page) as cdp:
        await cdp.dismiss_migration()
        await cdp.navigate(f"{get_e2e_ui_url()}/")
        await cdp.wait_app_layout()
        probe_js = f"""(async () => {{
          try {{
            await fetch({json.dumps(get_e2e_ui_url() + "/api/v1/features/voice_interaction/toggle")}, {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify({{ enabled: true }}),
            }});
            const resp = await fetch({json.dumps(get_e2e_ui_url() + "/api/v1/tts/synthesize")}, {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify({{ text: 'edge parallel read aloud', provider: 'edge' }}),
            }});
            const blob = await resp.blob();
            return {{ status: resp.status, bytes: blob.size, tab: 'read-aloud' }};
          }} catch (err) {{
            return {{ status: null, bytes: 0, error: String(err), tab: 'read-aloud' }};
          }}
        }})()"""
        last: dict[str, object] = {}
        for _ in range(5):
            result = await cdp.eval(probe_js)
            last = result if isinstance(result, dict) else {"probeError": result}
            if (
                last.get("error") is None
                and last.get("status") == 200
                and int(last.get("bytes", 0)) > 0
            ):
                return last
            await asyncio.sleep(2.0)
    if not isinstance(last, dict):
        raise AssertionError(f"Read-aloud probe returned non-dict: {last}")
    return last


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_voice_settings_no_edge_banner_when_available(
    require_edge_tts_available: None,
) -> None:
    _ensure_voice_feature_enabled()
    write_e2e_session_snapshot(
        current_node="test_voice_settings_no_edge_banner_when_available",
        phase="body",
    )
    state = _chrome_probe_voice_settings_with_retry(
        progress_node="test_voice_settings_no_edge_banner_when_available",
    )

    assert state.get("hasVoicePanel") is True, state
    assert state.get("showEdgeBanner") is False, state
    assert state.get("onChannelsSettings") is True, state


@pytest.mark.integration
@pytest.mark.timeout(120)
def test_live_tts_synthesize_after_voice_config() -> None:
    _require_live_stack()
    if not _edge_tts_available():
        pytest.skip("edge_tts_available=false")

    _ensure_voice_feature_enabled()
    _put_edge_voice_config()
    req = urllib.request.Request(  # noqa: S310 - fixed loopback URL
        f"{get_e2e_api_url()}/api/v1/tts/synthesize",
        data=json.dumps({"text": "edge tts chrome e2e"}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - loopback only
        assert resp.status == 200
        body = resp.read(16)
    assert body[:3] == b"ID3" or (body[0] == 0xFF and (body[1] & 0xE0) == 0xE0)


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(300)
@pytest.mark.asyncio
async def test_read_aloud_edge_api_from_browser_context(
    require_edge_tts_available: None,
    chrome_page: tuple[ChromeMcpClient, McpPage],
) -> None:
    """Browser same-origin fetch to /tts/synthesize (ReadAloud API path via Next proxy)."""
    _seed_voice_and_personal_settings()

    client, page = chrome_page
    async with _McpSession(client, page) as cdp:
        await cdp.dismiss_migration()
        await cdp.navigate(f"{get_e2e_ui_url()}/")
        await cdp.wait_app_layout()

        result = await cdp.eval(
            f"""(async () => {{
              try {{
                await fetch({json.dumps(get_e2e_ui_url() + "/api/v1/features/voice_interaction/toggle")}, {{
                  method: 'POST',
                  headers: {{ 'Content-Type': 'application/json' }},
                  body: JSON.stringify({{ enabled: true }}),
                }});
                const resp = await fetch({json.dumps(get_e2e_ui_url() + "/api/v1/tts/synthesize")}, {{
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


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(420)
@pytest.mark.asyncio
async def test_edge_tts_parallel_tabs_isolated(_require_live_e2e_lease: None) -> None:
    """Parallel tabs: voice banner (tab A) + read-aloud fetch (tab B) on shared stack."""
    _require_live_stack()
    if not _edge_tts_available():
        pytest.skip("edge_tts_available=false")

    _seed_voice_and_personal_settings()
    _ensure_voice_feature_enabled()

    client = ChromeMcpClient(request_timeout_sec=180.0)
    await asyncio.to_thread(client.start)
    page_timeout_ms = _CHROME_NEW_PAGE_TIMEOUT_MS

    try:
        voice_tab = await asyncio.to_thread(
            client.new_page,
            f"{get_e2e_ui_url()}/",
            timeout_ms=page_timeout_ms,
        )
        read_tab = await asyncio.to_thread(
            client.new_page,
            f"{get_e2e_ui_url()}/",
            timeout_ms=page_timeout_ms,
        )
        voice_result = await _probe_voice_banner(client, voice_tab)
        read_result = await _probe_read_aloud_fetch(client, read_tab)
    finally:
        await asyncio.to_thread(client.close)

    assert voice_result.get("hasVoicePanel") is True, voice_result
    assert voice_result.get("showEdgeBanner") is False, voice_result
    assert read_result.get("error") is None, read_result
    assert read_result.get("status") == 200, read_result
    assert int(read_result.get("bytes", 0)) > 0, read_result


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_live_health_info_includes_local_stt() -> None:
    _require_live_stack()
    info = _http_json("GET", f"{get_e2e_api_url()}/api/v1/health/info")
    assert isinstance(info, dict)
    assert "local_stt_available" in info
    assert isinstance(info["local_stt_available"], bool)


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_live_stt_status_reflects_local_install() -> None:
    _require_live_stack()
    status = _http_json("GET", f"{get_e2e_api_url()}/api/v1/stt/status")
    assert isinstance(status, dict)
    assert "available" in status
    assert isinstance(status["available"], bool)
    if _local_stt_available():
        assert status["available"] is True


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_voice_settings_no_local_banner_when_available(
    require_local_stt_available: None,
) -> None:
    _ensure_voice_feature_enabled()
    _put_local_voice_config()
    write_e2e_session_snapshot(
        current_node="test_voice_settings_no_local_banner_when_available",
        phase="body",
    )
    state = _chrome_probe_voice_settings_with_retry(
        progress_node="test_voice_settings_no_local_banner_when_available",
    )

    assert state.get("hasVoicePanel") is True, state
    assert state.get("showLocalSttBanner") is False, state
    assert state.get("onChannelsSettings") is True, state
