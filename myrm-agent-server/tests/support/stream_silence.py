"""A chat page's agent stream that the product holds silent, watched from inside the page.

The probe wraps the page's own ``fetch`` of ``/agents/agent-stream`` and records what the browser receives (application data,
keep-alive frames, the end of the stream), every change of the chat store's ``loading`` flag, and what the stream watchdog
logs. It can swallow the keep-alive frames before the page's stream consumer sees them: the same wire, but a page that is
never told the server is alive.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: page script evaluation and polling)

[OUTPUT]
- HEARTBEAT_FRAME: the exact bytes the server sends when a turn has been idle for a keep-alive interval
- install_stream_probe(): start watching before the message is sent
- wait_for_stream_log(): the log once the stream has ended
- StreamLog, Silence, longest_silence(), loading_falls(): what the log says

[POS]
Used by tests/e2e/test_stream_silence_chrome_e2e.py to prove a page stays busy through a turn that sends nothing for a minute
because the server's keep-alive frames reach its stream consumer, and recovers after the watchdog's window when they do not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, wait_for_state

HEARTBEAT_FRAME = "event: heartbeat\ndata: null\n\n"

_STREAM_END_TIMEOUT_SEC = 240.0

_PROBE_JS = """((swallowHeartbeats, heartbeatFrame) => {
  if (window.__streamProbe) return true;
  const store = window.__myrmChatStore;
  if (!store) return false;
  const origin = performance.now();
  const at = () => Math.round(performance.now() - origin);
  const probe = { chunks: [], loading: [], watchdog: [] };
  window.__streamProbe = probe;

  let loading = store.getState().loading;
  probe.loading.push([at(), loading]);
  store.subscribe((state) => {
    if (state.loading === loading) return;
    loading = state.loading;
    probe.loading.push([at(), loading]);
  });

  for (const level of ['warn', 'error']) {
    const write = console[level].bind(console);
    console[level] = (...args) => {
      const line = args.map(String).join(' ');
      if (line.startsWith('[StreamWatchdog]')) probe.watchdog.push(line.slice(0, 240));
      write(...args);
    };
  }

  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  const fetchOriginal = window.fetch.bind(window);
  let streams = 0;
  window.fetch = async (input, init) => {
    const response = await fetchOriginal(input, init);
    const url = String(input && input.url ? input.url : input);
    if (!url.includes('/agents/agent-stream') || !response.body) return response;
    const stream = ++streams;
    const reader = response.body.getReader();
    const body = new ReadableStream({
      async pull(controller) {
        for (;;) {
          const { value, done } = await reader.read();
          if (done) {
            probe.chunks.push([at(), 'eof', stream]);
            controller.close();
            return;
          }
          const parts = decoder.decode(value, { stream: true }).split(heartbeatFrame);
          const data = parts.join('');
          for (let beat = 1; beat < parts.length; beat++) probe.chunks.push([at(), 'heartbeat', stream]);
          if (data) probe.chunks.push([at(), 'data', stream]);
          if (parts.length === 1 || !swallowHeartbeats) {
            controller.enqueue(value);
            return;
          }
          if (data) {
            controller.enqueue(encoder.encode(data));
            return;
          }
        }
      },
      cancel: (reason) => reader.cancel(reason),
    });
    return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
  };
  return true;
})"""

_READ_LOG_JS = """(() => {
  const probe = window.__streamProbe;
  if (!probe) return { ready: false };
  return {
    ready: probe.chunks.some(([, kind]) => kind === 'eof'),
    chunks: probe.chunks,
    loading: probe.loading,
    watchdog: probe.watchdog,
  };
})()"""


@dataclass(frozen=True)
class Chunk:
    at_ms: int
    kind: str  # "data", "heartbeat" or "eof"
    stream: int


@dataclass(frozen=True)
class StreamLog:
    chunks: tuple[Chunk, ...]
    loading: tuple[tuple[int, bool], ...]  # (when, the flag's new value); the first entry is its value when the probe started
    watchdog: tuple[str, ...]


@dataclass(frozen=True)
class Silence:
    """A stretch in which a stream carried no application data."""

    start_ms: int  # the last chunk before it
    end_ms: int  # the next chunk after it
    heartbeats: tuple[int, ...]  # the keep-alive frames the server sent within it

    @property
    def length_ms(self) -> int:
        return self.end_ms - self.start_ms


def _whole_number(value: object) -> int:
    assert isinstance(value, int) and not isinstance(value, bool), f"not a whole number: {value!r}"
    return value


def _rows(state: dict[str, object], key: str) -> list[list[object]]:
    rows = state.get(key)
    assert isinstance(rows, list), f"the page's {key} log is missing: {state}"
    assert all(isinstance(row, list) for row in rows), f"the page's {key} log holds a row that is no list: {rows}"
    return rows


def parse_stream_log(state: dict[str, object]) -> StreamLog:
    """The page's log, checked: a malformed one fails the test instead of passing it."""
    watchdog = state.get("watchdog")
    assert isinstance(watchdog, list) and all(isinstance(line, str) for line in watchdog), f"watchdog log malformed: {state}"
    return StreamLog(
        chunks=tuple(Chunk(_whole_number(at), str(kind), _whole_number(stream)) for at, kind, stream in _rows(state, "chunks")),
        loading=tuple((_whole_number(at), bool(busy)) for at, busy in _rows(state, "loading")),
        watchdog=tuple(str(line) for line in watchdog),
    )


def install_stream_probe(client: ChromeMcpClient, page: McpPage, *, swallow_heartbeats: bool) -> None:
    """Start watching; call before the message is sent so the stream the page opens for it is wrapped."""
    script = f"({_PROBE_JS})({json.dumps(swallow_heartbeats)}, {json.dumps(HEARTBEAT_FRAME)})"
    installed = client.evaluate(page, script, timeout_sec=15.0)
    assert installed is True, f"the chat page holds no chat store to watch: {installed!r}"


def wait_for_stream_log(client: ChromeMcpClient, page: McpPage) -> StreamLog:
    """The log of the page's stream once it has ended."""
    return parse_stream_log(wait_for_state(client, page, _READ_LOG_JS, timeout_sec=_STREAM_END_TIMEOUT_SEC))


def longest_silence(log: StreamLog) -> Silence | None:
    """The longest gap between two chunks that are not keep-alive frames, within one stream."""
    longest: Silence | None = None
    for stream in sorted({chunk.stream for chunk in log.chunks}):
        own = [chunk for chunk in log.chunks if chunk.stream == stream]
        flowing = [chunk for chunk in own if chunk.kind != "heartbeat"]
        for before, after in zip(flowing, flowing[1:], strict=False):
            beats = tuple(c.at_ms for c in own if c.kind == "heartbeat" and before.at_ms < c.at_ms < after.at_ms)
            gap = Silence(before.at_ms, after.at_ms, beats)
            if longest is None or gap.length_ms > longest.length_ms:
                longest = gap
    return longest


def loading_falls(log: StreamLog) -> tuple[int, ...]:
    """When the page stopped being busy: each time ``loading`` went from true to false."""
    return tuple(now[0] for before, now in zip(log.loading, log.loading[1:], strict=False) if before[1] and not now[1])
