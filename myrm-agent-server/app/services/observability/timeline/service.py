"""[INPUT]
- myrm_agent_harness.observability.timeline_visualizer: TaskExecutionTimelineCollector, TimelineStepNode, TimelineIOMetrics

[OUTPUT]
- TaskTimelineInspectorService: Server-side business service managing live task inspectors and barge-in interrupts

[POS]
Server observability business service for live task execution inspection and skill call timeline analysis.
"""

from __future__ import annotations

import logging
import threading
from typing import ClassVar

from myrm_agent_harness.observability.timeline_visualizer import (
    TaskExecutionTimelineCollector,
    TimelineIOMetrics,
    TimelineNodeType,
    TimelineStepNode,
)

logger = logging.getLogger(__name__)


class TaskTimelineInspectorService:
    """Singleton service tracking active task execution timelines and dispatching barge-in interrupts."""

    _instance: ClassVar[TaskTimelineInspectorService | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._collectors: dict[str, TaskExecutionTimelineCollector] = {}
        self._interruption_ledger: dict[str, list[dict[str, str]]] = {}
        self._state_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> TaskTimelineInspectorService:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def get_or_create_collector(self, task_id: str) -> TaskExecutionTimelineCollector:
        with self._state_lock:
            if task_id not in self._collectors:
                # Keep active ledger bounded to avoid memory leaks
                if len(self._collectors) > 200:
                    oldest_key = next(iter(self._collectors))
                    del self._collectors[oldest_key]
                self._collectors[task_id] = TaskExecutionTimelineCollector(task_id=task_id)
            return self._collectors[task_id]

    def record_step(
        self,
        task_id: str,
        step_name: str,
        node_type: TimelineNodeType = "tool_invocation",
        parent_id: str | None = None,
        input_payload: dict[str, str] | None = None,
    ) -> str:
        collector = self.get_or_create_collector(task_id)
        return collector.start_step(
            step_name=step_name,
            node_type=node_type,
            parent_id=parent_id,
            input_payload=input_payload,
        )

    def complete_step(
        self,
        task_id: str,
        node_id: str,
        output_payload: dict[str, str] | None = None,
        metrics: TimelineIOMetrics | None = None,
    ) -> None:
        collector = self.get_or_create_collector(task_id)
        collector.complete_step(node_id=node_id, output_payload=output_payload, metrics=metrics)

    def fail_step(self, task_id: str, node_id: str, error_message: str) -> None:
        collector = self.get_or_create_collector(task_id)
        collector.fail_step(node_id=node_id, error_message=error_message)

    def interrupt_task(
        self,
        task_id: str,
        reason: str = "user_barge_in",
        barge_in_instruction: str | None = None,
    ) -> dict[str, str | int]:
        collector = self.get_or_create_collector(task_id)
        interrupted_nodes = 0

        # Interrupt any currently running nodes
        for node in collector.get_waterfall_nodes():
            if node.status == "running":
                collector.interrupt_step(node.node_id, reason=reason)
                interrupted_nodes += 1

        with self._state_lock:
            if task_id not in self._interruption_ledger:
                self._interruption_ledger[task_id] = []
            self._interruption_ledger[task_id].append(
                {
                    "reason": reason,
                    "instruction": barge_in_instruction or "",
                }
            )

        logger.info(f"Interrupted task '{task_id}' (interrupted {interrupted_nodes} active steps), reason: {reason}")

        return {
            "task_id": task_id,
            "interrupted_steps_count": interrupted_nodes,
            "status": "interrupted",
            "instruction": barge_in_instruction or "",
        }

    def get_timeline_snapshot(self, task_id: str) -> dict[str, object]:
        collector = self.get_or_create_collector(task_id)
        tree = collector.get_timeline_tree()
        waterfall = collector.get_waterfall_nodes()
        summary = collector.get_summary_stats()

        with self._state_lock:
            interruptions = list(self._interruption_ledger.get(task_id, []))

        return {
            "task_id": task_id,
            "tree": [self._serialize_node(n) for n in tree],
            "waterfall": [self._serialize_node(n) for n in waterfall],
            "summary": summary,
            "interruptions": interruptions,
        }

    @classmethod
    def _serialize_node(cls, node: TimelineStepNode) -> dict[str, object]:
        return {
            "node_id": node.node_id,
            "step_name": node.step_name,
            "parent_id": node.parent_id,
            "step_index": node.step_index,
            "node_type": node.node_type,
            "status": node.status,
            "start_time_ms": node.start_time_ms,
            "end_time_ms": node.end_time_ms,
            "duration_ms": node.duration_ms,
            "input_payload": node.input_payload,
            "output_payload": node.output_payload,
            "metrics": {
                "input_chars": node.metrics.input_chars,
                "output_chars": node.metrics.output_chars,
                "prompt_tokens": node.metrics.prompt_tokens,
                "completion_tokens": node.metrics.completion_tokens,
                "cache_hit": node.metrics.cache_hit,
            },
            "error_message": node.error_message,
            "children": [cls._serialize_node(c) for c in node.children],
        }
