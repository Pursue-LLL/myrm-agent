"""Agent stream accumulator for eval runs.

[INPUT]
- myrm_agent_harness.agent.errors::ToolErrorCategory (POS: canonical tool error categories)
- myrm_agent_harness.eval.protocols::AgentResponse (POS: result record returned by an eval AgentExecutor)
- myrm_agent_harness.agent.streaming.answer_draft::AnswerDraft (POS: streamed answer text honouring the restart contract)

[OUTPUT]
- StreamTrace: folds the agent event stream of one eval case into an ``AgentResponse``
  (answer text, tool trajectory, limit marker, decontamination block count, token usage).

[POS]
Pure event-to-response folding for ``LocalEvalExecutor``; owns no I/O and no agent wiring.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from myrm_agent_harness.agent.errors import ToolErrorCategory
from myrm_agent_harness.agent.streaming.answer_draft import AnswerDraft
from myrm_agent_harness.eval.protocols import AgentResponse


@dataclass(slots=True)
class StreamTrace:
    """Accumulates the events of a single eval case and renders the final response."""

    answer: AnswerDraft = field(default_factory=AnswerDraft)
    tools_called: list[str | dict[str, object]] = field(default_factory=list)
    tool_call_details: list[dict[str, object]] = field(default_factory=list)
    limit_reached: str | None = None
    blocked_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def consume(self, event: Mapping[str, object]) -> None:
        """Fold one stream event into the trace; unknown event types are ignored."""
        event_type = event.get("type", "")
        self.answer.feed(event)

        if event_type == "tasks_steps":
            self._record_tool_step(event)
        elif event_type == "engine_limit_reached":
            data = event.get("data")
            if isinstance(data, dict):
                limit_type = str(data.get("limit_type", "") or "")
                if limit_type:
                    self.limit_reached = limit_type
        elif event_type == "iteration_limit_reached":
            # The harness emits this when the LangGraph recursion
            # budget (the benchmark-declared ``max_iterations`` turn
            # ceiling, doubled to graph nodes) is reached;
            # engine_limit_reached only covers tool-call and replan
            # caps, so without this branch iteration-truncated cases
            # would silently lose their limit marker.
            self.limit_reached = "max_iterations"
        elif event_type == "token_usage":
            # The harness emits token events as {"usage": {"prompt_tokens": ...,
            # "completion_tokens": ..., ...}}; the usage dict never carries
            # input_tokens/output_tokens aliases, so read the canonical keys.
            data = event.get("data")
            if isinstance(data, dict):
                usage = data.get("usage")
                if isinstance(usage, dict):
                    self.input_tokens += int(usage.get("prompt_tokens") or 0)
                    self.output_tokens += int(usage.get("completion_tokens") or 0)

    def to_response(self, *, elapsed_ms: float) -> AgentResponse:
        """Render the accumulated trace as the eval framework's response record."""
        return AgentResponse(
            answer=self.answer.text,
            tools_called=self.tools_called,
            tool_call_details=self.tool_call_details,
            limit_reached=self.limit_reached,
            blocked_count=self.blocked_count,
            extra_timings={"execution_ms": elapsed_ms},
            token_usage={
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.input_tokens + self.output_tokens,
            },
        )

    def _record_tool_step(self, event: Mapping[str, object]) -> None:
        tool_name = str(event.get("tool_name", "")) or str(event.get("step_key", ""))
        if tool_name:
            self.tools_called.append(tool_name)
        # Record a per-step summary (tool name + step data) so the
        # eval report can disclose the action trajectory — the same
        # TASKS_STEPS payload the frontend renders live. Error steps
        # carry a structured ``error_category`` (e.g. the benchmark
        # decontamination guard) which lets the run count
        # pollution-guard engagement.
        step_detail: dict[str, object] = {
            "tool_name": tool_name,
            "step_key": str(event.get("step_key", "") or ""),
        }
        step_data = event.get("data")
        if isinstance(step_data, list) and step_data:
            step_detail["detail"] = step_data
        if event.get("status") == "error":
            step_detail["error"] = str(event.get("error", "") or "")[:300]
        raw_error_category = event.get("error_category")
        if isinstance(raw_error_category, str) and raw_error_category:
            step_detail["error_category"] = raw_error_category
        self.tool_call_details.append(step_detail)
        if event.get("error_category") == ToolErrorCategory.BENCHMARK_BLOCKED.value:
            self.blocked_count += 1
