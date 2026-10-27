"""Harness stream event handling for ChannelAgentExecutor.

[INPUT]
- app.core.channel_bridge.executor_helpers::StreamAccumulator, step_to_label (POS: Stream accumulation for channel turns.)
- app.channels.types::FissionTopologyUpdate, ProgressUpdate, StreamingText, ToolStep (POS: Channel message types.)
- agent_executor.approval_card::build_approval_card (POS: the localized approval card with its time limit)
- llms.errors.classifier::ErrorKind (POS: LLM error classification)
- agent_executor.deliverable::collect_channel_artifacts (POS: Artifact delivery helpers for ChannelAgentExecutor.)

[OUTPUT]
- iter_channel_stream_progress: maps harness stream events to channel progress yields (a tool approval becomes the card
  worded for ``locale``, carrying its time limit as ``ProgressUpdate.expiry``); answer text goes through
  ``acc.draft`` so a recovery that replays the in-flight segment does not duplicate it;
  capability_gap web_search not_configured|unreachable → ProgressUpdate; a fatal ``error`` event
  leaves its raw text (operator logs) and its error kind (member-facing wording) on the accumulator

[POS]
Stream event loop extracted from ChannelAgentExecutor.execute_stream. Converts
harness agent.process_stream events into ProgressUpdate/StreamingText for IM routing.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterable

from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

from app.channels.types import FissionTopologyUpdate, ProgressUpdate, StreamingText, ToolStep
from app.core.channel_bridge.executor_helpers import StreamAccumulator, step_to_label

from .approval_card import build_approval_card
from .deliverable import collect_channel_artifacts


async def iter_channel_stream_progress(
    events: AsyncIterable[dict[str, object]],
    acc: StreamAccumulator,
    *,
    locale: str,
) -> AsyncGenerator[ProgressUpdate | StreamingText | FissionTopologyUpdate, None]:
    """Map harness stream events to channel progress updates and streaming text."""
    first_message_seen = False

    async for event in events:
        event_type = event.get("type", "")
        # Streams answer text and applies the restart contract (a recovery replays only the in-flight segment).
        acc.draft.feed(event)

        if event_type == "fission_topology":
            topology = event.get("data")
            if isinstance(topology, FissionTopologyUpdate):
                yield topology

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

            yield StreamingText(text=acc.draft.text)

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
                yield build_approval_card(data, locale=locale)

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
            await asyncio.to_thread(collect_channel_artifacts, event, acc)

        elif event_type == "error":
            _record_fatal_error(event, acc)

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
            if tool_id == "web_search" and reason in (
                "not_configured",
                "unreachable",
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


def _record_fatal_error(event: dict[str, object], acc: StreamAccumulator) -> None:
    """Keep the raw error text for the operator log and the error kind that picks the member-facing wording."""
    error_msg = str(event.get("error", "Unknown error"))
    error_type = str(event.get("error_type", ""))
    acc.error_message = f"{error_type}: {error_msg}" if error_type else error_msg
    try:
        acc.error_kind = ErrorKind(event.get("error_kind"))
    except ValueError:
        acc.error_kind = ErrorKind.UNKNOWN
