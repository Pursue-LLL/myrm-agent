"""Replays the failures the previous stack was recorded on and reduces each to the verdicts the agent acts on.

[INPUT]
- golden_failures_baseline.json (POS: every served failure with the previous stack's verdict on it)
- golden_replay (POS: the in-memory provider and the adapter a replay goes through)
- errors (POS: the classifiers the agent's recovery reads)

[OUTPUT]
- HttpCase / StreamCase / FailureBaseline: the shapes of the baseline entries; load_baseline reads the committed file
- replay_http / replay_streams: {case id: verdict} of the installed stack for every recorded case

[POS]
The failures a settings screen, a gateway or a provider outage really produce: an error status with its body, an error
event inside a 200 stream, a stream cut off on the way, an empty one. What the agent does next (repeat, switch key,
compact, give up) is decided by five facts, so those are what is compared: the failover reason, the error kind, whether
the context window or the request size is exhausted, whether the quota is spent and how long the provider asked to
wait. The committed ``golden_failures_baseline.json`` was recorded by serving each case from a loopback HTTP server to
the previous chat adapter (litellm 1.97.0, the version the server's uv.lock pins and the product runs, at main
c0cbd9185d) and reducing the exception it raised with the classifiers of that stack's own errors package. The baseline's
``_meta.cross_check`` states how the harness lock's litellm 1.106.0 reads the same corpus.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from enum import Enum
from pathlib import Path
from typing import Literal, TypedDict, cast

import httpx

from myrm_agent_harness.toolkits.llms import errors

from .golden_compare import Verdict
from .golden_replay import case_of, model_for, replaying


class HttpCase(TypedDict):
    wire: str
    status: int
    headers: dict[str, str]
    body: str
    old: Verdict


class StreamCase(TypedDict):
    wire: str
    mode: Literal["normal", "truncate"]
    body: str
    old: Verdict


class FailureBaseline(TypedDict):
    http: dict[str, HttpCase]
    stream: dict[str, StreamCase]


def load_baseline() -> FailureBaseline:
    document = json.loads((Path(__file__).parent / "golden_failures_baseline.json").read_text(encoding="utf-8"))
    return cast(FailureBaseline, document)


class _CutOff(httpx.AsyncByteStream):
    """A body the provider stops sending half way: the connection closes before the body is complete."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def __aiter__(self) -> AsyncIterator[bytes]:
        if self._payload:
            yield self._payload
        raise httpx.RemoteProtocolError("peer closed connection without sending complete message body")


def _plain(value: object) -> object:
    return value.value if isinstance(value, Enum) else value


def failure_facts(exc: Exception) -> Verdict:
    return {
        "reason": _plain(errors.classify_failover_reason(exc)),
        "kind": _plain(errors.classify_error(exc)),
        "ctx": errors.is_context_overflow(exc),
        "payload": errors.is_payload_overflow(exc),
        "quota": errors.is_quota_exhausted(exc),
    }


def replay_http(cases: Mapping[str, HttpCase]) -> dict[str, Verdict]:
    def respond(request: httpx.Request) -> httpx.Response:
        case = cases[case_of(request)]
        content_type = "application/json" if case["body"].startswith(("{", "[")) else "text/html"
        headers = {**case["headers"], "content-type": content_type}
        return httpx.Response(case["status"], headers=headers, content=case["body"].encode())

    async def run() -> dict[str, Verdict]:
        verdicts: dict[str, Verdict] = {}
        for name, case in cases.items():
            try:
                await model_for(case["wire"], name).ainvoke("ping")
                verdicts[name] = {"outcome": "RETURNED"}
            except Exception as exc:  # what an adapter raises is exactly what is being classified
                verdicts[name] = {**failure_facts(exc), "retry_after": errors.extract_retry_after(exc)}
        return verdicts

    with replaying(respond):
        return asyncio.run(run())


def replay_streams(cases: Mapping[str, StreamCase]) -> dict[str, Verdict]:
    def respond(request: httpx.Request) -> httpx.Response:
        case = cases[case_of(request)]
        headers = {"content-type": "text/event-stream"}
        payload = case["body"].encode()
        if case["mode"] == "truncate":
            return httpx.Response(200, headers=headers, stream=_CutOff(payload))
        return httpx.Response(200, headers=headers, content=payload)

    async def run() -> dict[str, Verdict]:
        verdicts: dict[str, Verdict] = {}
        for name, case in cases.items():
            received: list[str] = []
            try:
                async for chunk in model_for(case["wire"], name, streaming=True).astream("ping"):
                    received.append(chunk.content if isinstance(chunk.content, str) else json.dumps(chunk.content))
                verdicts[name] = {"outcome": "COMPLETED", "text": "".join(received)}
            except Exception as exc:  # what an adapter raises is exactly what is being classified
                verdicts[name] = {"outcome": "RAISED", "partial": "".join(received), **failure_facts(exc)}
        return verdicts

    with replaying(respond):
        return asyncio.run(run())
