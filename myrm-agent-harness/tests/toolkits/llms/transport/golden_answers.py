"""Replays the recorded provider answers and reduces each message to what the agent reads.

[INPUT]
- golden_answers_baseline.json (POS: every served answer with the message the baseline returned for it)
- golden_replay (POS: the in-memory provider and the adapter a replay goes through)

[OUTPUT]
- AnswerCase: the shape of a baseline entry; load_baseline reads the committed file
- replay_answers: {case id: verdict} of the installed stack for every recorded case; a verdict is ``{"outcome":
  "raised"}`` or ``{"outcome": "returned", ...}`` with the facts of the message

[POS]
The answers that decide what a user sees and what a turn costs: the text, the tool calls (a call's name and
arguments), the finish reason, the token counts (cache reads and writes, reasoning), the reasoning text, and whether
the call raised at all. The cases are the shapes each wire really sends (tool use, cache usage, thinking blocks, blocked
prompts, truncated outputs, a body that is no answer) in the form of a plain JSON body, a server-sent-event stream or
an NDJSON stream. The committed ``golden_answers_baseline.json`` was recorded by serving each case from a loopback HTTP
server to the litellm chat adapter at main c0cbd9185d (litellm 1.97.0, the version the server's uv.lock pinned there)
and reducing the message it returned. The baseline's ``_meta.cross_check`` states how the harness
lock's litellm 1.106.0 reads the same corpus.
"""

from __future__ import annotations

import asyncio
import functools
import json
import operator
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, TypedDict, cast

import httpx
from langchain_core.messages import AIMessage

from .golden_compare import Verdict
from .golden_replay import case_of, model_for, replaying

_CONTENT_TYPES = {
    "json": "application/json",
    "sse": "text/event-stream",
    "ndjson": "application/x-ndjson",
    "html": "text/html",
    "text": "text/plain",
}


class AnswerCase(TypedDict):
    wire: str
    kind: Literal["json", "sse", "ndjson", "html", "text"]
    body: object
    old: Verdict | Literal["raised"]


def load_baseline() -> dict[str, AnswerCase]:
    document = json.loads((Path(__file__).parent / "golden_answers_baseline.json").read_text(encoding="utf-8"))
    return cast(dict[str, AnswerCase], document["cases"])


def recorded(case: AnswerCase) -> Verdict:
    """The recorded outcome in the same form a replay reports."""
    old = case["old"]
    return {"outcome": "raised"} if old == "raised" else {"outcome": "returned", **old}


def _plain_content(content: str | list[str | dict[str, object]]) -> str:
    return content if isinstance(content, str) else json.dumps(content, sort_keys=True, ensure_ascii=False)


def read(message: AIMessage) -> Verdict:
    """What the agent reads of an answer: text, tool calls, finish reason, token counts and reasoning."""
    usage = message.usage_metadata or {}
    calls = message.tool_calls or []
    return {
        "outcome": "returned",
        "content": _plain_content(message.content),
        "tool_calls": sorted([call["name"], json.dumps(call["args"], sort_keys=True)] for call in calls),
        "tool_id_thought": any("__thought__" in str(call.get("id")) for call in calls),
        "invalid_tool_calls": len(message.invalid_tool_calls or []),
        "finish": (message.response_metadata or {}).get("finish_reason"),
        "in": usage.get("input_tokens"),
        "out": usage.get("output_tokens"),
        "total": usage.get("total_tokens"),
        "cache_read": (usage.get("input_token_details") or {}).get("cache_read"),
        "cache_creation": (usage.get("input_token_details") or {}).get("cache_creation"),
        "reasoning_tokens": (usage.get("output_token_details") or {}).get("reasoning"),
        "reasoning_content": (message.additional_kwargs or {}).get("reasoning_content"),
        "thinking_blocks": len((message.additional_kwargs or {}).get("thinking_blocks") or []),
    }


def replay_answers(cases: Mapping[str, AnswerCase]) -> dict[str, Verdict]:
    def respond(request: httpx.Request) -> httpx.Response:
        case = cases[case_of(request)]
        body = json.dumps(case["body"]) if case["kind"] == "json" else str(case["body"])
        return httpx.Response(200, headers={"content-type": _CONTENT_TYPES[case["kind"]]}, content=body.encode())

    async def run() -> dict[str, Verdict]:
        verdicts: dict[str, Verdict] = {}
        for name, case in cases.items():
            streamed = case["kind"] in {"sse", "ndjson"}
            llm = model_for(case["wire"], name, streaming=streamed)
            try:
                if streamed:
                    chunks = [chunk async for chunk in llm.astream("ping")]
                    message = functools.reduce(operator.add, chunks)
                else:
                    message = await llm.ainvoke("ping")
                verdicts[name] = read(message)
            except Exception:  # whether an adapter raises at all is one of the recorded facts
                verdicts[name] = {"outcome": "raised"}
        return verdicts

    with replaying(respond):
        return asyncio.run(run())
