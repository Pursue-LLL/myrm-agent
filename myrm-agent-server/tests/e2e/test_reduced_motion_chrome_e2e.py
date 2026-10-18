"""Chrome E2E: the WebUI collapses motion when the OS asks for reduced motion.

Prerequisites:
  ./myrm ready --attach --chrome

Covers the guard chain this task shipped, against the real dev server:
  T1 - With no preference an infinite decorative animation really runs (so T2 cannot pass vacuously).
  T2 - Under prefers-reduced-motion:reduce the same element collapses to 0.01ms and one iteration.
  T3 - Flipping the preference on a loaded page takes effect without a reload, both directions.
  T4 - `animationend` still fires under reduce, which is the contract Radix overlays unmount by.

Why a raw CDP target instead of the mux client: Chrome allows one CDP client per target, and this
harness's orchestrator owns the page it creates. `Emulation.setEmulatedMedia` therefore has to run
on a target we created ourselves, otherwise the orchestrator's session is displaced. The page
under test is still the real dev server; only the client differs.
"""

from __future__ import annotations

import json
import time
import urllib.request

import pytest

_CDP_BASE = 'http://127.0.0.1:9333'
_UI_URL = 'http://127.0.0.1:3000/'

# Reads the first running pulse plus the media query state. `found` distinguishes "no element yet"
# from "element covered by the guard", which is what makes T2 meaningful.
_PROBE_JS = """(() => {
  const nodes = Array.from(document.querySelectorAll('.animate-pulse'));
  const node = nodes.find((n) => getComputedStyle(n).animationName !== 'none');
  return {
    found: Boolean(node),
    duration: node ? getComputedStyle(node).animationDuration : null,
    iterations: node ? getComputedStyle(node).animationIterationCount : null,
    reduced: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    href: location.href,
  };
})()"""

# Under reduce an animation must still dispatch `animationend`; Radix `usePresence` unmounts
# overlays by matching that event, so a guard written as `animation: none` would break dialogs.
_ANIMATION_END_JS = """new Promise((resolve) => {
  const style = document.createElement('style');
  style.textContent = '@keyframes probeKf{from{opacity:0}to{opacity:1}} .probe-anim{animation:probeKf 2s linear 1}';
  document.head.appendChild(style);
  const el = document.createElement('div');
  el.className = 'probe-anim';
  el.style.cssText = 'position:fixed;top:-9999px;width:10px;height:10px';
  let fired = false;
  el.addEventListener('animationend', () => { fired = true; }, { once: true });
  document.body.appendChild(el);
  const cs = getComputedStyle(el);
  setTimeout(() => resolve({
    fired,
    duration: cs.animationDuration,
    iterations: cs.animationIterationCount,
  }), 1500);
})"""


class _Target:
    """One raw CDP target with a tiny command helper."""

    def __init__(self) -> None:
        from e2e_core.effect_guard import assert_http_effect_allowed

        _new_target_url = f'{_CDP_BASE}/json/new?about:blank'
        assert_http_effect_allowed(method='PUT', url=_new_target_url)
        request = urllib.request.Request(_new_target_url, method='PUT')
        self._info = json.load(urllib.request.urlopen(request, timeout=15))
        from websockets.sync.client import connect

        self._ws = connect(
            self._info['webSocketDebuggerUrl'], open_timeout=15, close_timeout=5, max_size=None
        )
        self._seq = 0

    def send(self, method: str, params: dict | None = None, timeout: float = 40.0) -> dict:
        self._seq += 1
        message_id = self._seq
        self._ws.send(json.dumps({'id': message_id, 'method': method, 'params': params or {}}))
        while True:
            message = json.loads(self._ws.recv(timeout=timeout))
            if message.get('id') == message_id:
                return message

    def js(self, expression: str, timeout: float = 40.0) -> object:
        result = self.send(
            'Runtime.evaluate',
            {'expression': expression, 'returnByValue': True, 'awaitPromise': True},
            timeout=timeout,
        )
        payload = result.get('result', {})
        if payload.get('exceptionDetails'):
            raise AssertionError(f"page raised: {payload['exceptionDetails']}")
        return payload.get('result', {}).get('value')

    def set_reduced_motion(self, value: str) -> None:
        self.send(
            'Emulation.setEmulatedMedia',
            {'features': [{'name': 'prefers-reduced-motion', 'value': value}]},
        )

    def wait_for_pulse(self, *, timeout_sec: float = 90.0) -> dict:
        deadline = time.monotonic() + timeout_sec
        last: dict = {}
        while time.monotonic() < deadline:
            value = self.js(_PROBE_JS)
            if isinstance(value, dict):
                last = value
                if last.get('found'):
                    return last
            time.sleep(0.5)
        raise AssertionError(f'page never rendered a running pulse: {last!r}')

    def close(self) -> None:
        try:
            self._ws.close()
        finally:
            try:
                urllib.request.urlopen(f'{_CDP_BASE}/json/close/{self._info["id"]}', timeout=5)
            except OSError:
                pass


def _seconds(value: str) -> float:
    """Computed durations arrive as `2s`, `1e-05s` or `0.01ms`."""
    text = str(value).strip()
    if text.endswith('ms'):
        return float(text[:-2]) / 1000.0
    if text.endswith('s'):
        return float(text[:-1])
    raise AssertionError(f'unexpected computed duration: {value!r}')


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_webui_collapses_motion_when_the_os_asks() -> None:
    """The shipped guard must actually stop motion in a real browser, in both directions."""
    target = _Target()
    try:
        target.send('Page.enable')

        # T1: the baseline must really animate, otherwise T2 proves nothing.
        target.set_reduced_motion('no-preference')
        target.send('Page.navigate', {'url': _UI_URL})
        normal = target.wait_for_pulse()
        assert normal['reduced'] is False, normal
        assert _seconds(normal['duration']) > 0.1, f"no real animation: {normal!r}"
        assert normal['iterations'] == 'infinite', f"not an infinite loop: {normal!r}"

        # T2: same element, preference on, still the same document.
        target.set_reduced_motion('reduce')
        time.sleep(1.0)
        reduced = target.js(_PROBE_JS)
        assert isinstance(reduced, dict)
        assert reduced['reduced'] is True, f"reduce emulation did not reach the page: {reduced!r}"
        assert _seconds(reduced['duration']) <= 0.001, f"guard did not shorten: {reduced!r}"
        assert reduced['iterations'] == '1', f"guard did not cap iterations: {reduced!r}"

        # T3: flipping back must restore motion without a reload (the same live document).
        target.set_reduced_motion('no-preference')
        time.sleep(1.0)
        restored = target.js(_PROBE_JS)
        assert isinstance(restored, dict)
        assert restored['reduced'] is False
        assert _seconds(restored['duration']) > 0.1, f"motion did not come back: {restored!r}"
        assert restored['iterations'] == 'infinite', f"loop did not come back: {restored!r}"

        # T4: under reduce the animation must still end, or Radix overlays never unmount.
        target.set_reduced_motion('reduce')
        time.sleep(0.5)
        ended = target.js(_ANIMATION_END_JS, timeout=20.0)
        assert isinstance(ended, dict), ended
        assert ended['fired'] is True, f"animationend did not fire under reduce: {ended!r}"
        assert _seconds(ended['duration']) <= 0.001, ended
    finally:
        target.close()
