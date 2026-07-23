"""Harness stream event handling for ChannelAgentExecutor.

[INPUT]
- app.core.channel_bridge.executor_helpers::StreamAccumulator, step_to_label (POS: Stream accumulation for channel turns.)
- app.channels.types::ProgressUpdate, StreamingText, QuickReply, ToolStep (POS: Channel message types.)
- agent_executor.artifact_deep_links::collect_channel_artifacts (POS: Artifact delivery helpers for channel executor.)

[OUTPUT]
- ChannelStreamEventState: mutable side-effect holder for approval timeout metadata
- iter_channel_stream_progress: maps harness stream events to channel progress yields;
  capability_gap surface_unavailable / web_search not_configured|unreachable → ProgressUpdate

[POS]
Stream event loop extracted from ChannelAgentExecutor.execute_stream. Converts
harness agent.process_stream events into ProgressUpdate/StreamingText for IM routing.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterable
from dataclasses import dataclass, field

from app.channels.types import ProgressUpdate, QuickReply, StreamingText, ToolStep
from app.core.channel_bridge.executor_helpers import StreamAccumulator, step_to_label

from .artifact_deep_links import collect_channel_artifacts


@dataclass
class ChannelStreamEventState:
    """Side effects produced while consuming the harness event stream."""

    approval_timeout_info: dict[str, object] | None = field(default=None)


async def iter_channel_stream_progress(
    events: AsyncIterable[dict[str, object]],
    acc: StreamAccumulator,
    state: ChannelStreamEventState,
) -> AsyncGenerator[ProgressUpdate | StreamingText | object, None]:
    """Map harness stream events to channel progress updates and streaming text."""
    first_message_seen = False

    async for event in events:
        event_type = event.get("type", "")

        if event_type == "fission_topology":
            yield event["data"]

        elif event_type == "tasks_steps":
            step_key = str(event.get("step_key", ""))
            label = step_to_label(step_key, event)
            if label:
                yield ProgressUpdate(label=label)
                tool_name = str(event.get("tool_name") or "") or step_key
                acc.tool_steps.append(ToolStep(name=tool_name, label=label))

        elif event_type == "reasoning" and isinstance(event.get("data"), str):
            acc.reasoning_chunks.append(str(event["data"]))

        elif event_type == "message" and isinstance(event.get("data"), str):
            if not first_message_seen:
                first_message_seen = True
                yield ProgressUpdate(label="✍️ Writing response...")

            acc.chunks.append(str(event["data"]))
            yield StreamingText(text="".join(acc.chunks))

        elif event_type == "sources" and isinstance(event.get("data"), list):
            raw_src = event.get("data")
            assert isinstance(raw_src, list)
            src_items: list[dict[str, object]] = []
            for el in raw_src:
                if isinstance(el, dict):
                    src_items.append({str(k): val for k, val in el.items()})
            acc.add_sources(src_items)

        elif event_type == "tool_approval_request":
            data = event.get("data", {})
            if isinstance(data, dict):
                action_requests = data.get("actionRequests", [])
                extensions = data.get("extensions", {})
                timeout_info = extensions.get("timeout", {}) if isinstance(extensions, dict) else {}
                timeout_secs = timeout_info.get("seconds", 300) if isinstance(timeout_info, dict) else 300
                timeout_behavior = timeout_info.get("behavior", "deny") if isinstance(timeout_info, dict) else "deny"

                if isinstance(action_requests, list) and action_requests:
                    tool_names = [str(req.get("action", "unknown")) for req in action_requests if isinstance(req, dict)]
                    reasons = [
                        str(req.get("description", ""))
                        for req in action_requests
                        if isinstance(req, dict) and req.get("description")
                    ]
                    tools_str = ", ".join(tool_names) if tool_names else "unknown"
                    reason_str = "; ".join(reasons) if reasons else ""
                else:
                    tools_str = str(data.get("tool_name", "unknown"))
                    reason_str = str(data.get("reason", ""))

                timeout_action = "auto-approve" if timeout_behavior == "allow" else "auto-deny"
                label = f"{tools_str} needs approval: {reason_str}\n⏱ Timeout: {timeout_secs}s ({timeout_action})"

                is_batch = isinstance(action_requests, list) and len(action_requests) > 1
                quick_replies: tuple[QuickReply, ...] = (
                    QuickReply(label="✅ Approve", text="/approve", required=True),
                    QuickReply(label="❌ Deny", text="/deny", required=True),
                )
                if is_batch:
                    quick_replies = (
                        QuickReply(
                            label="✅ Approve All",
                            text="/approve",
                            required=True,
                        ),
                        QuickReply(label="❌ Deny All", text="/deny", required=True),
                        QuickReply(
                            label="📋 Batch",
                            text=f"/batch {','.join('a' for _ in action_requests)}",
                            required=True,
                        ),
                    )
                yield ProgressUpdate(label=label, quick_replies=quick_replies)
                state.approval_timeout_info = {
                    "seconds": timeout_secs,
                    "behavior": timeout_behavior,
                }

        elif event_type == "tool_image_output":
            img_data = event.get("data", {})
            if isinstance(img_data, dict):
                if img_data.get("base64"):
                    acc.last_image_base64 = str(img_data["base64"])
                    acc.last_image_url = None
                elif img_data.get("url"):
                    acc.last_image_url = str(img_data["url"])
                    acc.last_image_base64 = None
                acc.last_image_mime = str(img_data.get("mime_type", "image/jpeg"))
                acc.last_image_tool = str(event.get("tool_name", ""))

        elif event_type == "artifacts":
            collect_channel_artifacts(event, acc)

        elif event_type == "error":
            error_msg = str(event.get("error", "Unknown error"))
            error_type = str(event.get("error_type", ""))
            acc.error_message = f"{error_type}: {error_msg}" if error_type else error_msg

        elif event_type == "token_usage":
            data = event.get("data")
            if isinstance(data, dict):
                cost = data.get("cost_usd")
                if isinstance(cost, (int, float)):
                    acc.cost_usd += float(cost)
                model = data.get("model_name")
                if isinstance(model, str) and model:
                    acc.model_name = model
                usage = data.get("usage")
                if isinstance(usage, dict):
                    total = usage.get("total_tokens")
                    if isinstance(total, int) and total > 0:
                        acc.total_tokens += total

        elif event_type == "capability_gap":
            data = event.get("data", {})
            if not isinstance(data, dict):
                continue
            reason = str(data.get("reason") or "")
            tool_id = str(data.get("tool_id") or "")
            if reason == "surface_unavailable":
                from app.services.agent.stream_session.entitlement_gap_preflight import (
                    resolve_surface_unavailable_display_message,
                )

                display_message = str(data.get("display_message") or "").strip()
                if not display_message:
                    display_message = resolve_surface_unavailable_display_message(None)
                yield ProgressUpdate(label=display_message)
            elif (
                tool_id == "web_search"
                and reason in ("not_configured", "unreachable")
            ):
                from app.services.agent.stream_session.entitlement_gap_preflight import (
                    resolve_web_search_config_gap_display_message,
                )

                display_message = str(data.get("display_message") or "").strip()
                if not display_message:
                    display_message = resolve_web_search_config_gap_display_message(
                        reason=reason,
                        locale=None,
                    )
                yield ProgressUpdate(label=display_message)

        elif event_type == "message_end":
            end_cost = event.get("cost_usd")
            if isinstance(end_cost, (int, float)) and end_cost > 0 and acc.cost_usd == 0:
                acc.cost_usd = float(end_cost)
            end_model = event.get("model")
            if isinstance(end_model, str) and end_model and not acc.model_name:
                acc.model_name = end_model
