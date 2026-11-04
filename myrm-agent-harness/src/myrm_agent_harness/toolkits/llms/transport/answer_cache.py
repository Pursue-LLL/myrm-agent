"""Answer cache: a provider request that was already answered is answered from memory for an hour.

[INPUT]
- transport.http (POS: PreparedRequest, Chunk, StreamDecoder and the provider stream iterators)

[OUTPUT]
- AnswerCache / answer_cache: the bounded, process-wide store of provider answers
- request_key: the identity of one provider request
- CHAT / RESPONSES: which answers of each wire are worth replaying
- cached_answer / acached_answer: serve or file the answer of a non-streaming request
- cached_stream / acached_stream: replay or record the chunks of a streaming request
- ReplayStream / AsyncReplayStream: a stored stream handed out like a provider stream

[POS]
Chat, Responses, embedding and rerank calls repeat verbatim in practice (a retried utility prompt, a chunk embedded
twice, a ranking asked again), and the provider charges for each repeat. The cache keeps the answer of a finished
request for an hour (200 entries, 1 MiB each) and hands it back, as a fresh copy, to the next request that is
identical on the wire: endpoint, credentials, headers and body. Only an answer that finished normally and says
something is kept, so a failure, a truncated answer, a refusal or an empty reply is always asked again. A stream is
recorded by its decoder and filed when the provider ends it, so a stream the consumer abandons or a connection that
breaks is never filed. ``MYRM_LLM_ANSWER_CACHE=0`` switches the cache off.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Final

from myrm_agent_harness.toolkits.llms.transport.http import (
    AsyncProviderStream,
    Chunk,
    PreparedRequest,
    ProviderStream,
    StreamDecoder,
    finish_reason_of,
)

logger = logging.getLogger(__name__)

SWITCH_ENV: Final = "MYRM_LLM_ANSWER_CACHE"
MAX_ENTRIES: Final = 200
TTL_SECONDS: Final = 3600.0
MAX_ENTRY_CHARS: Final = 1_048_576
_OFF_WORDS: Final = frozenset({"0", "false", "no", "off"})
_NORMAL_ENDINGS: Final = frozenset({"stop", "tool_calls", "function_call"})


class AnswerCache:
    """Bounded store of serialized answers: entries expire after the TTL and the least recently used one goes first."""

    def __init__(
        self,
        *,
        enabled: bool,
        max_entries: int = MAX_ENTRIES,
        ttl_seconds: float = TTL_SECONDS,
        max_entry_chars: int = MAX_ENTRY_CHARS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.enabled = enabled
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._max_entry_chars = max_entry_chars
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, text = entry
            if self._clock() >= expires_at:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return text

    def put(self, key: str, text: str) -> None:
        if len(text) > self._max_entry_chars:
            return
        with self._lock:
            self._entries[key] = (self._clock() + self._ttl_seconds, text)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


answer_cache: Final = AnswerCache(enabled=os.getenv(SWITCH_ENV, "1").strip().lower() not in _OFF_WORDS)


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def request_key(request: PreparedRequest) -> str | None:
    """Identity of a request as the provider sees it; ``None`` for a multipart upload, which is never replayed."""
    if request.body is None:
        return None
    wire = [request.provider, request.url, request.stream, dict(request.query), dict(request.headers), request.body]
    text = json.dumps(wire, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Policy:
    """What is worth replaying from one wire: an answer that finished normally and carries something."""

    answer: Callable[[Mapping[str, object]], bool]
    carries_output: Callable[[Chunk], bool]
    finished: Callable[[str | None, Chunk], bool]


def _chat_answer(answer: Mapping[str, object]) -> bool:
    choices = answer.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else None
    if not isinstance(first, Mapping) or first.get("finish_reason") not in _NORMAL_ENDINGS:
        return False
    message = first.get("message")
    return isinstance(message, Mapping) and bool(message.get("content") or message.get("tool_calls"))


def _chat_chunk_output(chunk: Chunk) -> bool:
    choices = chunk.get("choices")
    for choice in choices if isinstance(choices, list) else []:
        delta = choice.get("delta") if isinstance(choice, Mapping) else None
        if isinstance(delta, Mapping) and (delta.get("content") or delta.get("tool_calls")):
            return True
    return False


CHAT: Final = Policy(
    answer=_chat_answer,
    carries_output=_chat_chunk_output,
    finished=lambda finish_reason, _last: finish_reason in _NORMAL_ENDINGS,
)
RESPONSES: Final = Policy(
    answer=lambda answer: answer.get("status") == "completed" and bool(answer.get("output")),
    carries_output=lambda chunk: str(chunk.get("type") or "").startswith("response.output_"),
    finished=lambda _finish_reason, last: last.get("type") == "response.completed",
)


def _stored(request: PreparedRequest) -> tuple[str | None, str | None]:
    """(key, stored answer) of a request; no key when the cache is off or the request is never replayed."""
    if not answer_cache.enabled:
        return None, None
    key = request_key(request)
    stored = None if key is None else answer_cache.get(key)
    if stored is not None:
        logger.debug("Provider answer served from the cache (provider=%s)", request.provider)
    return key, stored


def _file(key: str, answer: object) -> None:
    try:
        text = _dump(answer)
    except (TypeError, ValueError):
        logger.debug("Provider answer is not plain JSON; it is not cached")
        return
    answer_cache.put(key, text)


def cached_answer[T](
    request: PreparedRequest, produce: Callable[[], T], *, keep: Callable[[T], bool] | None = None
) -> T:
    """The answer of a non-streaming request: the stored copy if there is one, else ``produce()``, filed if ``keep``."""
    key, stored = _stored(request)
    if stored is not None:
        return json.loads(stored)  # type: ignore[no-any-return]
    answer = produce()
    if key is not None and (keep is None or keep(answer)):
        _file(key, answer)
    return answer


async def acached_answer[T](
    request: PreparedRequest, produce: Callable[[], Awaitable[T]], *, keep: Callable[[T], bool] | None = None
) -> T:
    """Async twin of :func:`cached_answer`."""
    key, stored = _stored(request)
    if stored is not None:
        return json.loads(stored)  # type: ignore[no-any-return]
    answer = await produce()
    if key is not None and (keep is None or keep(answer)):
        _file(key, answer)
    return answer


class _RecordingDecoder:
    """Hands a decoder's chunks through while recording them; the provider ending the stream files the recording."""

    __slots__ = ("_chars", "_finish", "_inner", "_key", "_last", "_output", "_overflowed", "_policy", "_texts")

    def __init__(self, inner: StreamDecoder, key: str, policy: Policy) -> None:
        self._inner = inner
        self._key = key
        self._policy = policy
        self._texts: list[str] = []
        self._chars = 0
        self._finish: str | None = None
        self._output = False
        self._overflowed = False
        self._last: Chunk | None = None

    @property
    def done(self) -> bool:
        return self._inner.done

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        return self._record(self._inner.feed(event, data))

    def finish(self) -> list[Chunk]:
        chunks = self._record(self._inner.finish())
        self._file()
        return chunks

    def _record(self, chunks: list[Chunk]) -> list[Chunk]:
        for chunk in chunks:
            self._last = chunk
            self._finish = finish_reason_of(chunk) or self._finish
            if self._overflowed:
                continue
            text = _dump(chunk)
            self._chars += len(text)
            if self._chars > MAX_ENTRY_CHARS:
                self._overflowed = True
                self._texts.clear()
                continue
            self._texts.append(text)
            self._output = self._output or self._policy.carries_output(chunk)
        return chunks

    def _file(self) -> None:
        last = self._last
        if last is None or self._overflowed or not self._output or not self._policy.finished(self._finish, last):
            return
        answer_cache.put(self._key, f'{{"finish":{_dump(self._finish)},"chunks":[{",".join(self._texts)}]}}')


class ReplayStream:
    """The chunks of an earlier identical stream, handed out the way a provider stream hands them out."""

    def __init__(self, chunks: list[Chunk], finish_reason: str | None) -> None:
        self.received_finish_reason = finish_reason
        self._chunks = iter(chunks)

    def __iter__(self) -> ReplayStream:
        return self

    def __next__(self) -> Chunk:
        return next(self._chunks)

    def close(self) -> None:
        self._chunks = iter(())


class AsyncReplayStream:
    """Async twin of :class:`ReplayStream`."""

    def __init__(self, chunks: list[Chunk], finish_reason: str | None) -> None:
        self.received_finish_reason = finish_reason
        self._chunks = iter(chunks)

    def __aiter__(self) -> AsyncReplayStream:
        return self

    async def __anext__(self) -> Chunk:
        try:
            return next(self._chunks)
        except StopIteration:
            raise StopAsyncIteration from None

    async def aclose(self) -> None:
        self._chunks = iter(())


def cached_stream(
    open_stream: Callable[[PreparedRequest, StreamDecoder], ProviderStream],
    request: PreparedRequest,
    decoder: StreamDecoder,
    policy: Policy,
) -> ProviderStream | ReplayStream:
    """The chunks of a streaming request: replayed if an identical stream was stored, else live and recorded."""
    key, stored = _stored(request)
    if stored is not None:
        entry = json.loads(stored)
        return ReplayStream(entry["chunks"], entry["finish"])
    return open_stream(request, decoder if key is None else _RecordingDecoder(decoder, key, policy))


async def acached_stream(
    open_stream: Callable[[PreparedRequest, StreamDecoder], Awaitable[AsyncProviderStream]],
    request: PreparedRequest,
    decoder: StreamDecoder,
    policy: Policy,
) -> AsyncProviderStream | AsyncReplayStream:
    """Async twin of :func:`cached_stream`."""
    key, stored = _stored(request)
    if stored is not None:
        entry = json.loads(stored)
        return AsyncReplayStream(entry["chunks"], entry["finish"])
    return await open_stream(request, decoder if key is None else _RecordingDecoder(decoder, key, policy))
