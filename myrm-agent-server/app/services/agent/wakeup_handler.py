"""Harness async wakeup bridge — headless continuation on the single-user server.

[INPUT]
- app.services.agent.params::AgentRequest / convert_to_general_agent_params (POS: chat config → GeneralAgentParams)
- app.ai_agents::AgentFactory (POS: instantiate GeneralAgent for headless SSE-equivalent runs)
- app.core.utils.chat_utils::convert_chat_history (POS: frontend-style chat tuples → LangChain messages)
- ChatService history persistence primitives

[OUTPUT]
- ServerWakeupHandler.on_async_wakeup / _run_headless_agent: append async result notifications and rerun GeneralAgent streams through AgentGateway headless queues.

[POS]
Business orchestration hook for Harness `ASYNC_WAKEUP`; runs per isolated server instance without Control Plane scheduling.
"""

import asyncio
import logging
import uuid
from typing import cast

from myrm_agent_harness.agent.sub_agents.types import SubAgentResult

from app.core.utils.chat_utils import convert_chat_history
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)


class ServerWakeupHandler:
    """Handles async wakeup events from the Harness framework in the background."""

    async def on_async_wakeup(
        self, result: SubAgentResult, agent_id: str, session_id: str | None
    ) -> None:
        """Called by Harness when a background subagent (wait=False) completes.

        This will:
        1. Append the subagent result to the chat session history.
        2. Trigger a new agent execution in the background.
        """
        if not session_id:
            logger.warning(
                "Wakeup handler received event without session_id. Ignoring."
            )
            return

        logger.info(
            f"🚀 ServerWakeupHandler received wakeup for session {session_id}, task {result.task_id}"
        )

        # We must schedule this as a background task to avoid blocking the harness cleanup hook
        asyncio.create_task(self._process_wakeup(result, agent_id, session_id))

    async def _process_wakeup(
        self, result: SubAgentResult, agent_id: str, session_id: str
    ) -> None:
        """Process the wakeup event in a detached background task."""
        try:
            # 1. Format the result
            status_str = "completed successfully" if result.success else "failed"
            content = f"Async subagent '{result.agent_type}' (task_id: {result.task_id}) {status_str}."
            if result.duration_seconds:
                content += f" Duration: {result.duration_seconds:.1f}s."
            if result.error:
                content += f"\nError: {result.error}"
            elif result.result:
                content += f"\nResult:\n{result.result}"

            content += "\n\nPlease continue your workflow or provide the final answer to the user based on this result."

            # 2. Append to chat history without overriding the existing prompt cache
            # (We use ChatService to append a system/tool message)
            from datetime import datetime, timezone

            # Since this is an internal system message injected for the agent's eyes only,
            # we use action_mode="system_event" or just append a user message with a specific format.
            # But the best way is to append it as a system/tool completion.
            # ChatService.ensure_chat_and_append_user_message is usually for human inputs.
            # We'll use append_user_message but prefix it to make it clear it's a system notification.
            system_notification = f"<system_notification type='async_result' task_id='{result.task_id}'>\n{content}\n</system_notification>"

            await ChatService.ensure_chat_and_append_user_message(
                chat_id=session_id,
                content=system_notification,
                sent_at=datetime.now(tz=timezone.utc),
                sent_timezone="UTC",
                message_id=f"wakeup_{result.task_id}",
                action_mode="general",
            )

            # 3. Trigger a background run
            # We construct a synthetic AgentRequest and call the pipeline
            # without an active HTTP Request object. We'll use a mocked Request or
            # call the underlying agent factory directly.
            await self._run_headless_agent(session_id, agent_id)

        except Exception as e:
            logger.error(
                f"Failed to process async wakeup for session {session_id}: {e}",
                exc_info=True,
            )

    async def _run_headless_agent(self, session_id: str, agent_id: str) -> None:
        """Run the agent headlessly without an active HTTP stream."""
        from app.services.budget.enforcer import should_block_execution

        if await should_block_execution():
            logger.warning(
                "Headless wakeup blocked: daily budget exceeded (block policy), session=%s",
                session_id,
            )
            return

        from app.ai_agents import AgentFactory
        from app.services.agent.params import (
            AgentRequest,
            convert_to_general_agent_params,
        )

        try:
            request = AgentRequest(
                message_id=str(uuid.uuid4()),
                chat_id=session_id,
                query="[SYSTEM WAKEUP]",
                action_mode="general",
                agent_id=agent_id,
            )

            # Load history
            chat_history = await ChatService.load_web_chat_history(
                session_id, api_key=None
            )

            normalized_history: list[list[str | dict[str, object]]] = []
            for turn in chat_history:
                row: list[str | dict[str, object]] = []
                for item in turn:
                    if isinstance(item, dict):
                        row.append({str(k): v for k, v in item.items()})
                    else:
                        row.append(item)
                normalized_history.append(row)

            params, _routing_tier, _, _archive_restore_results = await convert_to_general_agent_params(
                request, normalized_history
            )

            wakeup_payload: dict[str, object] = {"channel_name": "headless_wakeup"}
            if params.memory_channel_id is None:
                wakeup_payload["memory_channel_id"] = "web_chat"
            params = params.model_copy(update=wakeup_payload)

            agent = AgentFactory.create_general_agent(params)

            async def consume_stream() -> None:
                import json

                from app.services.agent.gateway import get_agent_gateway
                from app.services.agent.streaming_support.stream_collector import StreamContentCollector
                from app.services.chat.chat_service import ChatService
                from app.services.event.app_event_bus import (
                    AppEvent,
                    AppEventType,
                    get_event_bus,
                )

                bus = get_event_bus()
                gateway = get_agent_gateway()
                try:
                    converted_history = await convert_chat_history(params.chat_history)

                    max_retries = 3
                    for attempt in range(max_retries):
                        collector = StreamContentCollector()
                        try:
                            raw_stream = agent.process_stream(
                                query=cast(str | list[dict[str, object]], params.query),
                                chat_history=converted_history,
                                message_id=params.message_id,
                                chat_id=params.chat_id,
                                cancel_token=None,
                                timezone=params.timezone,
                                force_delegate_agent=params.force_delegate_agent,
                            )

                            # 使用 gateway.execute_stream 包装流，进行并发控制和超时保护
                            # 注意：为了让同一 session 能被唤醒，我们需要在 session_id 上加上后缀以绕过 ActiveSessionInfo 冲突，
                            # 这样同一个 session 的后台任务会互相排斥，但不会和前台活跃会话冲突。
                            headless_stream = gateway.execute_stream(
                                raw_stream,
                                agent_type="headless_wakeup",
                                session_id=(
                                    f"{session_id}_headless" if session_id else None
                                ),
                                agent_instance=agent,
                            )

                            async for chunk in headless_stream:
                                if isinstance(chunk, dict):
                                    payload = chunk
                                elif hasattr(chunk, "model_dump"):
                                    payload = chunk.model_dump()
                                elif hasattr(chunk, "to_dict"):
                                    payload = chunk.to_dict()
                                elif isinstance(chunk, str) and chunk.startswith(
                                    "data: "
                                ):
                                    try:
                                        payload = json.loads(chunk[6:].strip())
                                    except Exception:
                                        continue
                                else:
                                    import dataclasses

                                    if dataclasses.is_dataclass(chunk):
                                        payload = dataclasses.asdict(chunk)
                                    else:
                                        continue

                                collector.feed_event(payload)

                                bus.publish(
                                    AppEvent(
                                        event_type=AppEventType.ASYNC_AGENT_STREAM_CHUNK,
                                        data={
                                            "session_id": session_id,
                                            "chunk": payload,
                                        },
                                    )
                                )
                            logger.info(
                                f"✅ Headless wakeup agent run completed for session {session_id}"
                            )
                            break  # Success, exit retry loop
                        except Exception as e:
                            logger.error(
                                f"Headless wakeup stream error on attempt {attempt + 1}/{max_retries}: {e}"
                            )
                            if attempt < max_retries - 1:
                                await asyncio.sleep(
                                    2**attempt
                                )  # Exponential backoff: 1s, 2s
                            else:
                                logger.error(
                                    f"❌ Headless wakeup failed permanently for session {session_id} after {max_retries} attempts."
                                )
                finally:
                    if "collector" in locals() and collector.has_content and session_id:
                        await ChatService.persist_assistant_message_safe(
                            session_id,
                            collector.content,
                            extra_data=collector.extra_data,
                            timezone=params.timezone,
                        )
                    await agent.close()

            asyncio.create_task(consume_stream())

        except Exception as e:
            logger.error(
                f"Failed to start headless agent run for session {session_id}: {e}"
            )
