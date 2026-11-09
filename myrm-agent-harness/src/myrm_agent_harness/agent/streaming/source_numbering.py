"""Source numbering across the runs of one thread: a run's tracker starts from what the thread already told the model.

A run that continues a thread (an approval resume, the next turn) begins with a fresh ``SourceTracker``. Numbering from
one again would give the model two pages under one number: its context still holds the labels of the earlier runs, and
the cards of the earlier runs are still on screen. The tool interceptor stamps every hoisted source with the number
the model read it under (``stamp_source_indexes``); ``restore_source_numbering`` reads the stamps back from the
thread's checkpoint.

[INPUT]
- agent.middlewares.tooling.tool_sources_hoisting::TOOL_SOURCES_KWARG (POS: Last step of tool interception; the hoisted sources travel in additional_kwargs under this key)
- agent.streaming.source_tracker::SourceTracker (POS: Source reference forwarding capability for BaseAgent.)
- runtime.checkpointing.read_access::read_checkpoint_messages (POS: Read-side counterpart to factory.py, the single place that knows the checkpoint payload shape)

[OUTPUT]
- restore_source_numbering(): Seed a run's SourceTracker with the numbers its thread already stated

[POS]
Run-start step of the streaming layer: ``StreamExecutor.execute`` calls it right after binding the run's numbering,
so every tool of the run numbers on from the thread's earlier runs.
"""

from __future__ import annotations

from collections.abc import Mapping

from langchain_core.messages import ToolMessage
from langchain_core.runnables.config import RunnableConfig

from myrm_agent_harness.agent.middlewares.tooling.tool_sources_hoisting import TOOL_SOURCES_KWARG
from myrm_agent_harness.runtime.checkpointing.read_access import read_checkpoint_messages

from .source_tracker import SourceTracker


async def restore_source_numbering(
    tracker: SourceTracker, checkpointer: object | None, run_config: RunnableConfig
) -> None:
    """Seed ``tracker`` with the numbers the thread's stored tool messages record.

    A run without a checkpointer or a thread id, a thread nothing is stored for, and a thread that cannot be read
    (the read logs a warning) all leave the tracker numbering from one: the run itself goes on.
    """
    thread_id = run_config.get("configurable", {}).get("thread_id")
    if not isinstance(thread_id, str):
        return
    stated: list[Mapping[str, object]] = []
    for message in await read_checkpoint_messages(checkpointer, thread_id):
        if isinstance(message, ToolMessage):
            sources = message.additional_kwargs.get(TOOL_SOURCES_KWARG)
            if isinstance(sources, list):
                stated.extend(source for source in sources if isinstance(source, dict))
    tracker.restore(stated)
