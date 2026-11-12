"""A chat page's agent streams that the product holds silent or the network stops delivering, watched from inside the page.

The probe wraps the page's own ``fetch`` of ``/agents/agent-stream`` (the run) and of ``/agents/chat/<id>/attach`` (the stream a
page attaches to a live turn) and records every request, what the browser receives on each stream (application data, keep-alive
frames, the end of the stream, the page cancelling it), every change of the chat store's ``loading`` flag, and what the stream
watchdog logs. It can also stop delivering the first run stream some time after its data began to flow, and never close it: a
connection that died without telling anyone.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: page script evaluation and polling)
- myrm_agent_harness.agent.streaming.stream_buffer (POS: the keep-alive frame the server sends)

[OUTPUT]
- install_stream_probe(): start watching before the message is sent
- wait_for_stream_log() / STREAM_END_TIMEOUT_SEC: the log once a stream has ended, and how long a turn with a minute's silence is waited for
- StreamLog, Chunk, Request, Silence, longest_silence(), last_heard(), ended_at(), loading_falls(): what the log says

[POS]
Used by tests/e2e/test_stream_silence_chrome_e2e.py to prove a page stays busy through a turn that sends nothing for a minute
because the server's keep-alive frames keep arriving, and that a connection which stops delivering altogether is replaced by
the attach stream within the stream consumer's liveness budget.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from myrm_agent_harness.agent.streaming.stream_buffer import HEARTBEAT_FRAME

from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, wait_for_state

STREAM_END_TIMEOUT_SEC = 240.0

_PROBE_JS = """((stallAfterMs, heartbeatFrame) => {
  if (window.__streamProbe) return true;
  const store = window.__myrmChatStore;
  if (!store) return false;
  const origin = performance.now();
  const at = () => Math.round(performance.now() - origin);
  const probe = { chunks: [], requests: [], loading: [], watchdog: [] };
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

  const STALLED = Symbol('stalled');
  const forever = new Promise(() => {});
  const fetchOriginal = window.fetch.bind(window);
  let streams = 0;
  let stallPending = stallAfterMs !== null;
  const kindOf = (url) => {
    if (url.includes('/agents/agent-stream')) return 'run';
    return /\\/attach(\\?|$)/.test(url) && !url.includes('multiplexed=true') ? 'attach' : null;
  };
  window.fetch = async (input, init) => {
    const url = String(input && input.url ? input.url : input);
    const kind = kindOf(url);
    if (kind === null) return fetchOriginal(input, init);
    const stream = ++streams;
    probe.requests.push([at(), kind, stream]);
    const response = await fetchOriginal(input, init);
    if (!response.body) return response;

    // Only the first run stream loses its connection: stallAfterMs after its data began to flow, nothing more is delivered.
    let dies = null;
    let startCountdown = () => {};
    if (kind === 'run' && stallPending) {
      stallPending = false;
      dies = new Promise((resolve) => {
        let started = false;
        startCountdown = () => {
          if (started) return;
          started = true;
          setTimeout(() => resolve(STALLED), stallAfterMs);
        };
      });
    }
    const decoder = new TextDecoder();
    const reader = response.body.getReader();
    let cancelled = false;
    const body = new ReadableStream({
      async pull(controller) {
        const next = await (dies ? Promise.race([reader.read(), dies]) : reader.read());
        if (next === STALLED) {
          probe.chunks.push([at(), 'stalled', stream]);
          await forever;
        }
        const { value, done } = next;
        if (done) {
          // The page's own cancel ends the pending read the same way; only the server closing the stream is an end.
          if (cancelled) return;
          probe.chunks.push([at(), 'eof', stream]);
          controller.close();
          return;
        }
        const parts = decoder.decode(value, { stream: true }).split(heartbeatFrame);
        for (let beat = 1; beat < parts.length; beat++) probe.chunks.push([at(), 'heartbeat', stream]);
        if (parts.join('')) {
          probe.chunks.push([at(), 'data', stream]);
          startCountdown();
        }
        controller.enqueue(value);
      },
      cancel: (reason) => {
        cancelled = true;
        probe.chunks.push([at(), 'cancelled', stream]);
        return reader.cancel(reason);
      },
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
    requests: probe.requests,
    loading: probe.loading,
    watchdog: probe.watchdog,
  };
})()"""


@dataclass(frozen=True)
class Chunk:
    at_ms: int
    # "data", "heartbeat", "eof" (the server closed the stream), "cancelled" (the page gave up on it) or "stalled" (the moment
    # the probe stopped delivering the stream)
    kind: str
    stream: int


@dataclass(frozen=True)
class Request:
    at_ms: int
    kind: str  # "run" (the agent-stream request) or "attach"
    stream: int


@dataclass(frozen=True)
class StreamLog:
    chunks: tuple[Chunk, ...]
    requests: tuple[Request, ...]
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
        requests=tuple(
            Request(_whole_number(at), str(kind), _whole_number(stream)) for at, kind, stream in _rows(state, "requests")
        ),
        loading=tuple((_whole_number(at), bool(busy)) for at, busy in _rows(state, "loading")),
        watchdog=tuple(str(line) for line in watchdog),
    )


def install_stream_probe(client: ChromeMcpClient, page: McpPage, *, stall_after_ms: int | None = None) -> None:
    """Start watching; call before the message is sent so the stream the page opens for it is wrapped.

    With ``stall_after_ms`` the run stream stops delivering anything that long after its first application data.
    """
    script = f"({_PROBE_JS})({json.dumps(stall_after_ms)}, {json.dumps(HEARTBEAT_FRAME)})"
    installed = client.evaluate(page, script, timeout_sec=15.0)
    assert installed is True, f"the chat page holds no chat store to watch: {installed!r}"


def wait_for_stream_log(client: ChromeMcpClient, page: McpPage, *, timeout_sec: float = STREAM_END_TIMEOUT_SEC) -> StreamLog:
    """The log of the page's streams once one of them has ended; a timeout reports the log so far."""
    return parse_stream_log(wait_for_state(client, page, _READ_LOG_JS, timeout_sec=timeout_sec))


def longest_silence(log: StreamLog) -> Silence | None:
    """The longest gap between two chunks that are not keep-alive frames, within one stream."""
    longest: Silence | None = None
    for stream in sorted({chunk.stream for chunk in log.chunks}):
        own = [chunk for chunk in log.chunks if chunk.stream == stream]
        flowing = [chunk for chunk in own if chunk.kind in ("data", "eof")]
        for before, after in zip(flowing, flowing[1:], strict=False):
            beats = tuple(c.at_ms for c in own if c.kind == "heartbeat" and before.at_ms < c.at_ms < after.at_ms)
            gap = Silence(before.at_ms, after.at_ms, beats)
            if longest is None or gap.length_ms > longest.length_ms:
                longest = gap
    return longest


def last_heard(log: StreamLog, stream: int) -> int:
    """When the page last received anything on ``stream``, a keep-alive frame included."""
    heard = [chunk.at_ms for chunk in log.chunks if chunk.stream == stream and chunk.kind in ("data", "heartbeat")]
    assert heard, f"the page received nothing on stream {stream}: {log}"
    return max(heard)


def ended_at(log: StreamLog, stream: int) -> int | None:
    """When the server closed ``stream``; None while it did not (a stream that stalled or that the page cancelled never ends)."""
    ends = [chunk.at_ms for chunk in log.chunks if chunk.stream == stream and chunk.kind == "eof"]
    return min(ends) if ends else None


def loading_falls(log: StreamLog) -> tuple[int, ...]:
    """When the page stopped being busy: each time ``loading`` went from true to false."""
    return tuple(now[0] for before, now in zip(log.loading, log.loading[1:], strict=False) if before[1] and not now[1])
