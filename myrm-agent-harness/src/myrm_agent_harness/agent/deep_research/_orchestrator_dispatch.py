"""Research agent dispatch for the Deep Research orchestrator.

Runs the research agents of one orchestrator step in parallel, each on per-run guards of its own.

[INPUT]
- agent._internals._agent_helpers::ephemeral_run_scope (POS: isolated per-run guards for a nested run)
- agent.sub_agents.builder (POS: standalone research agent construction and tool filtering)
- helpers::build_research_subagent_config (POS: research sub-agent config)
- agent.streaming.types::AgentEventType (POS: status and source events)

[OUTPUT]
- DeepResearchDispatchMixin: Mixin providing _dispatch_research_agents.

[POS]
Parallel research agent dispatch for the Deep Research orchestrator: semaphore-bounded fan-out, per-agent
guard isolation, status and source streaming.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.utils.logger_utils import get_agent_logger

from .helpers import build_research_subagent_config

logger = get_agent_logger(__name__)

__all__ = ["DeepResearchDispatchMixin"]


class DeepResearchDispatchMixin:
    """Mixin providing the parallel dispatch of research agents.

    Expects host class to have:
    - _llm: BaseChatModel
    - _research_agent_llm: BaseChatModel | None
    - _config: DeepResearchConfig
    - _parent_tools: list[BaseTool]
    - _cancel_token: CancellationToken | None
    - _context: dict
    - _executor: object | None
    - _result: DeepResearchResult
    - _source_tracker: SourceTracker
    - _make_event(...): dict
    - _accumulate_child_usage(event): None
    """

    async def _dispatch_research_agents(
        self,
        tasks: list[dict[str, str]],
        message_id: str,
        event_queue: asyncio.Queue[dict[str, object]] | None = None,
    ) -> list[str]:
        """Run research sub-agents in parallel, returning their result texts.

        When event_queue is provided, sub-agent status events are pushed to it
        for real-time streaming to the client.
        """
        from myrm_agent_harness.agent._internals._agent_helpers import ephemeral_run_scope
        from myrm_agent_harness.agent.sub_agents.builder import (
            build_standalone_agent,
            filter_tools,
        )

        config = build_research_subagent_config(self._config)  # type: ignore[attr-defined]
        sem = asyncio.Semaphore(self._config.max_concurrent_agents)  # type: ignore[attr-defined]
        dispatch_id = uuid4().hex[:8]

        def _push_status(idx: int, task_text: str, status: str, **extra: object) -> None:
            if event_queue is None:
                return
            event_queue.put_nowait(
                self._make_event(  # type: ignore[attr-defined]
                    AgentEventType.STATUS,
                    message_id,
                    data={
                        "phase": "research",
                        "agent_index": idx,
                        "agent_status": status,
                        "task": task_text[:120],
                        **extra,
                    },
                )
            )

        async def run_one(task_text: str, idx: int) -> str:
            async with sem:
                _push_status(idx, task_text, "started")
                messages: list[str] = []
                scope_key = f"research-{dispatch_id}-{idx}"
                with ephemeral_run_scope(scope_key):
                    try:
                        filtered_tools = filter_tools(config, self._parent_tools)  # type: ignore[attr-defined]
                        child = build_standalone_agent(
                            llm=self._research_agent_llm or self._llm,  # type: ignore[attr-defined]
                            config=config,
                            tools=filtered_tools,
                            task_description=task_text,
                            executor=self._executor,  # type: ignore[attr-defined]
                        )
                        async for event in child.run(
                            query=task_text,
                            chat_history=[],
                            context=dict(self._context),  # type: ignore[attr-defined]
                            cancel_token=self._cancel_token,  # type: ignore[attr-defined]
                        ):
                            event_type = event.get("type")
                            if event_type == AgentEventType.MESSAGE.value:
                                content = event.get("data", "")
                                text = content if isinstance(content, str) else str(content)
                                messages.append(text)
                                if event_queue is not None:
                                    event_queue.put_nowait(
                                        self._make_event(  # type: ignore[attr-defined]
                                            AgentEventType.STATUS,
                                            message_id,
                                            data={
                                                "phase": "research",
                                                "agent_index": idx,
                                                "agent_status": "streaming",
                                                "task": task_text[:120],
                                                "content": text,
                                            },
                                        )
                                    )
                            elif event_type == AgentEventType.TOOL_START.value:
                                tool_name = event.get("tool_name", "")
                                _push_status(idx, task_text, "tool_call", tool_name=tool_name)
                            elif event_type == AgentEventType.SOURCES.value:
                                raw = event.get("data", [])
                                if isinstance(raw, list) and raw and event_queue is not None:
                                    deduped = self._source_tracker.add_batch(raw)  # type: ignore[attr-defined]
                                    if deduped:
                                        event_queue.put_nowait(
                                            self._make_event(  # type: ignore[attr-defined]
                                                AgentEventType.SOURCES, message_id, data=deduped
                                            )
                                        )
                            elif event_type == AgentEventType.MESSAGE_END.value:
                                self._accumulate_child_usage(event)  # type: ignore[attr-defined]
                            elif event_type == AgentEventType.ERROR.value:
                                err = event.get("error", "Unknown error")
                                logger.error("[deep-research] Research agent %d error: %s", idx, err)
                                if messages:
                                    partial = "".join(messages)
                                    self._result.agent_results.append(  # type: ignore[attr-defined]
                                        {"task": task_text, "result": partial, "partial": True}
                                    )
                                    _push_status(idx, task_text, "error", result_length=len(partial), partial=True)
                                    return f"{partial}\n\n[Partial — agent encountered error]"
                                _push_status(idx, task_text, "error")
                                return "[Research error]"

                        result_text = "".join(messages)
                        self._result.agent_results.append(  # type: ignore[attr-defined]
                            {"task": task_text, "result": result_text}
                        )
                        _push_status(idx, task_text, "complete", result_length=len(result_text))
                        logger.info("[deep-research] Agent %d completed: %d chars", idx, len(result_text))
                        return result_text or "[No findings]"

                    except Exception as e:
                        logger.error("[deep-research] Research agent %d failed: %s", idx, e, exc_info=True)
                        if messages:
                            partial = "".join(messages)
                            self._result.agent_results.append(  # type: ignore[attr-defined]
                                {"task": task_text, "result": partial, "partial": True}
                            )
                            _push_status(idx, task_text, "error", result_length=len(partial), partial=True)
                            return f"{partial}\n\n[Partial — agent failed]"
                        _push_status(idx, task_text, "error")
                        return "[Research agent failed]"

        coros = [run_one(t["task"], i) for i, t in enumerate(tasks)]
        return list(await asyncio.gather(*coros))
