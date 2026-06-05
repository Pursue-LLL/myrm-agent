"""SSE stream content collector for persisting assistant messages with metadata.

[INPUT]
JSON SSE chunks and parsed Agent stream events (POS: Agent runtime event stream)

[OUTPUT]
StreamContentCollector: collects assistant content and message extra_data, including memory citation refs and retrieval traces.

[POS]
Agent API persistence helper. Converts transient SSE events into durable Message.extra_data metadata.
"""

from __future__ import annotations

import asyncio
import json

_SSE_DATA_PREFIX = "data: "
_MEMORY_RECALL_TOOL_NAMES = frozenset(
    {"memory_recall", "memory_recall_tool"}
)  # TODO(2026-Q3): remove "memory_recall" legacy alias after migration settles
_PERSISTED_STATUS_STEP_KEYS = frozenset({"archive_restore_blocked", "archive_restore_result"})

ACTIVE_COLLECTORS: dict[str, "StreamContentCollector"] = {}


def _is_memory_recall_tool(tool_name: object) -> bool:
    return isinstance(tool_name, str) and tool_name in _MEMORY_RECALL_TOOL_NAMES


class StreamContentCollector:
    """Collects content and metadata from SSE stream events.

    Supports two input formats:
    - SSE string chunks (general_agent): feed_sse("data: {...}\\n\\n")
    - Event dicts (via gateway): feed_event({...})
    """

    def __init__(self, sibling_group_id: str | None = None, chat_id: str | None = None) -> None:
        self._content_parts: list[str] = []
        self._reasoning_parts: list[str] = []
        self._sources: list[dict[str, object]] = []
        self._progress_steps: list[dict[str, object]] = []
        self._cited_memory_ids: list[str] = []
        self._cited_memory_refs: list[dict[str, object]] = []
        self._memory_retrieval_traces: list[dict[str, object]] = []
        self._usage: dict[str, object] | None = None
        self._context_budget: dict[str, object] | None = None
        self._cost_usd: float | None = None
        self._cost_status: str | None = None
        self._completion_status: str | None = None
        self._model_name: str | None = None
        self._routing_tier: str | None = None
        self._privacy_level: str | None = None
        self._privacy_route: str | None = None
        self._cache_break: dict[str, object] | None = None
        self._token_economics: dict[str, object] | None = None
        self._usage_alert: dict[str, object] | None = None
        self._sibling_group_id: str | None = sibling_group_id
        self._chat_id: str | None = chat_id
        self._subscribers: list[asyncio.Queue[dict[str, object]]] = []

        if self._chat_id:
            ACTIVE_COLLECTORS[self._chat_id] = self

    def cleanup(self) -> None:
        """Remove from active collectors registry."""
        if self._chat_id and self._chat_id in ACTIVE_COLLECTORS:
            del ACTIVE_COLLECTORS[self._chat_id]

    def unsubscribe(self, q: asyncio.Queue[dict[str, object]]) -> None:
        """Remove a subscriber queue from the active subscriber list."""
        if q in self._subscribers:
            self._subscribers.remove(q)

    @property
    def has_subscribers(self) -> bool:
        """Check if there are active subscribers."""
        return len(self._subscribers) > 0

    def subscribe(self) -> tuple[dict[str, object], asyncio.Queue[dict[str, object]]]:
        """Atomically get current snapshot and subscribe to future events."""
        q: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        self._subscribers.append(q)

        # Merge progress steps by id to keep only the latest state
        merged_steps_dict: dict[str, dict[str, object]] = {}
        ordered_steps: list[dict[str, object]] = []
        for step in self._progress_steps:
            step_id = step.get("id")
            if isinstance(step_id, str):
                if step_id not in merged_steps_dict:
                    merged_steps_dict[step_id] = step.copy()
                    ordered_steps.append(merged_steps_dict[step_id])
                else:
                    merged_steps_dict[step_id].update(step)
            else:
                ordered_steps.append(step)

        # Merge sources by url to keep only unique sources
        merged_sources_dict: dict[str, dict[str, object]] = {}
        ordered_sources: list[dict[str, object]] = []
        for source in self._sources:
            url = source.get("url")
            if isinstance(url, str):
                if url not in merged_sources_dict:
                    merged_sources_dict[url] = source.copy()
                    ordered_sources.append(merged_sources_dict[url])
                else:
                    merged_sources_dict[url].update(source)
            else:
                ordered_sources.append(source)

        snapshot = {
            "content": "".join(self._content_parts),
            "reasoning": "".join(self._reasoning_parts),
            "progress_steps": ordered_steps,
            "sources": ordered_sources,
        }
        return snapshot, q

    def feed_sse(self, chunk: str) -> None:
        """Parse an SSE-formatted string chunk and collect data."""
        if not chunk.startswith(_SSE_DATA_PREFIX):
            return
        try:
            event = _string_keyed_dict(json.loads(chunk[len(_SSE_DATA_PREFIX) :].rstrip()))
            if event is None:
                return
            self._process_event(event)
            for q in self._subscribers:
                q.put_nowait(event)
        except (json.JSONDecodeError, TypeError):
            pass

    def feed_event(self, event: dict[str, object]) -> None:
        """Collect data from a pre-parsed event dict."""
        self._process_event(event)
        for q in self._subscribers:
            q.put_nowait(event)

    def _process_event(self, event: dict[str, object]) -> None:
        event_type = event.get("type")
        data = event.get("data")

        if event_type == "message" and data:
            self._content_parts.append(str(data))
        elif event_type == "reasoning" and data:
            self._reasoning_parts.append(str(data))
        elif event_type == "sources" and isinstance(data, list):
            self._sources.extend(_string_keyed_dicts(data))
        elif event_type == "tasks_steps":
            step = {
                "step_key": event.get("step_key"),
                "tool_name": event.get("tool_name"),
                "items": data,
                "count": event.get("count"),
            }
            self._progress_steps.append(step)
        elif event_type == "token_usage" and isinstance(data, dict):
            self._usage = _string_keyed_dict(data.get("usage"))

        elif event_type == "message_end":
            usage = _string_keyed_dict(event.get("usage"))
            if usage is not None:
                self._usage = usage
            token_economics = _string_keyed_dict(event.get("token_economics"))
            if token_economics is not None:
                self._token_economics = token_economics
            context_budget = _string_keyed_dict(event.get("context_budget"))
            if context_budget is not None:
                self._context_budget = context_budget
            cost = event.get("cost_usd")
            if isinstance(cost, (int, float)):
                self._cost_usd = float(cost)
            cost_status = event.get("cost_status")
            if isinstance(cost_status, str):
                self._cost_status = cost_status
            completion_status = event.get("completion_status")
            if isinstance(completion_status, str):
                self._completion_status = completion_status
            model = event.get("model")
            if isinstance(model, str):
                self._model_name = model
            usage_alert = _string_keyed_dict(event.get("usage_alert"))
            if usage_alert is not None:
                self._usage_alert = usage_alert
        elif event_type == "tool_stdout_chunk" and isinstance(data, str):
            # 实时终端流式输出事件，不持久化到数据库，仅透传给前端
            pass
        elif event_type == "tool_end":
            cited = event.get("cited_memory_ids")
            is_memory_recall = _is_memory_recall_tool(event.get("tool_name"))
            if is_memory_recall and isinstance(cited, list):
                for mid in cited:
                    if isinstance(mid, str) and mid not in self._cited_memory_ids:
                        self._cited_memory_ids.append(mid)
            refs = event.get("cited_memory_refs")
            if is_memory_recall and isinstance(refs, list):
                self._extend_cited_memory_refs(refs)
            trace = event.get("memory_retrieval_trace")
            if is_memory_recall and isinstance(trace, dict):
                self._append_memory_retrieval_trace(trace)
        elif event_type == "routing_decision" and isinstance(data, dict):
            tier = data.get("tier")
            if isinstance(tier, str):
                self._routing_tier = tier
        elif event_type == "privacy_level" and isinstance(data, dict):
            level = data.get("current_turn_level")
            if isinstance(level, str):
                self._privacy_level = level
        elif event_type == "privacy_route" and isinstance(data, dict):
            route = data.get("route")
            if isinstance(route, str):
                self._privacy_route = route
        elif event_type == "status":
            step_key = event.get("step_key")
            if step_key == "cache_break" and isinstance(data, dict):
                self._cache_break = data
            if isinstance(step_key, str) and step_key in _PERSISTED_STATUS_STEP_KEYS:
                step = {
                    "step_key": step_key,
                    "tool_name": event.get("tool_name"),
                    "items": event.get("items"),
                    "status": event.get("status"),
                }
                if isinstance(data, dict):
                    archive_restore_block = _string_keyed_dict(data.get("archive_restore_block"))
                    if archive_restore_block is not None:
                        step["archive_restore_block"] = archive_restore_block
                    archive_restore_result = _string_keyed_dict(data.get("archive_restore_result"))
                    if archive_restore_result is not None:
                        step["archive_restore_result"] = archive_restore_result
                self._progress_steps.append(step)

    @property
    def content(self) -> str:
        return "".join(self._content_parts)

    @property
    def reasoning(self) -> str | None:
        return "".join(self._reasoning_parts) if self._reasoning_parts else None

    @property
    def has_content(self) -> bool:
        return bool(self._content_parts) or bool(self._reasoning_parts)

    @property
    def sibling_group_id(self) -> str | None:
        return self._sibling_group_id

    @property
    def extra_data(self) -> dict[str, object] | None:
        """Build extra_data dict for DB storage. Returns None if empty."""
        result: dict[str, object] = {}
        if self._sources:
            result["sources"] = self._sources
        if self._progress_steps:
            result["progressSteps"] = self._progress_steps
        if self._usage:
            result["usage"] = self._usage
        if self._context_budget:
            result["contextBudget"] = self._context_budget
        if self._cost_usd is not None:
            result["costUsd"] = self._cost_usd
        if self._cost_status:
            result["costStatus"] = self._cost_status
        if self._completion_status:
            result["completionStatus"] = self._completion_status

        # Extract usage alert if present
        if hasattr(self, "_usage_alert") and self._usage_alert:
            result["usageAlert"] = self._usage_alert

        if self._model_name:
            result["modelName"] = self._model_name
        if self._token_economics:
            result["tokenEconomics"] = self._token_economics
        if self._routing_tier:
            result["routingTier"] = self._routing_tier
        if self._privacy_level:
            result["privacyLevel"] = self._privacy_level
        if self._privacy_route:
            result["privacyRoute"] = self._privacy_route
        if self._cache_break:
            result["cacheBreak"] = self._cache_break
        if self._cited_memory_ids:
            result["citedMemoryIds"] = self._cited_memory_ids
        if self._cited_memory_refs:
            result["citedMemoryRefs"] = self._cited_memory_refs
        if self._memory_retrieval_traces:
            result["memoryRetrievalTraces"] = self._memory_retrieval_traces
        if self.reasoning:
            result["reasoning"] = self.reasoning
        return result or None

    def _extend_cited_memory_refs(self, refs: list[object]) -> None:
        seen = {str(ref.get("id")) for ref in self._cited_memory_refs if isinstance(ref.get("id"), str)}
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            ref_id = ref.get("id")
            if not isinstance(ref_id, str) or not ref_id or ref_id in seen:
                continue
            normalized = {str(key): value for key, value in ref.items() if isinstance(key, str)}
            self._cited_memory_refs.append(normalized)
            seen.add(ref_id)

    def _append_memory_retrieval_trace(self, trace: dict[object, object]) -> None:
        trace_id = trace.get("id")
        if not isinstance(trace_id, str) or not trace_id:
            return
        if any(existing.get("id") == trace_id for existing in self._memory_retrieval_traces):
            return
        normalized = {str(key): value for key, value in trace.items() if isinstance(key, str)}
        self._memory_retrieval_traces.append(normalized)


def _string_keyed_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items() if isinstance(key, str)}


def _string_keyed_dicts(values: list[object]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for value in values:
        normalized = _string_keyed_dict(value)
        if normalized is not None:
            result.append(normalized)
    return result
