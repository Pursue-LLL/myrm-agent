"""Phase and multi-lane execution stepper tracking for streaming sessions.

Maps agent runtime events into standardized 3-phase and 6-lane lifecycle transitions
according to the production agent execution specification (Nodes 1-30).

[INPUT]
- Streaming chunk dictionaries or event types

[OUTPUT]
- Standardized phase_transition dictionaries for SSE emission
"""

from __future__ import annotations

import time
from typing import Final

_MCP_MARKERS: Final[tuple[str, ...]] = ("mcp__", "skills.mcp_")
_SKILL_MARKERS: Final[tuple[str, ...]] = ("skills.", "skill_")
_USER_HITL_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "ask_question",
        "interactive_feedback",
        "approval_request",
        "confirm_action",
    }
)
_SANDBOX_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "bash",
        "bash_tool",
        "python_execute",
        "write_file",
        "read_file",
        "list_dir",
        "grep_search",
        "glob_find",
    }
)


# The UI renders ``node_label`` verbatim, so the labels follow the chat locale.
_PLANNING_LABELS = {"en": "Request understanding & safety planning", "zh": "请求理解与安全规划"}
_LLM_EXEC_LABELS = {"en": "Model reasoning & strategy generation", "zh": "大模型推理与策略生成"}
_LLM_PLAN_LABELS = {"en": "Intent & context reasoning", "zh": "意图与上下文推理"}
_APPROVAL_LABELS = {"en": "Waiting for user confirmation & approval", "zh": "等待用户确认与审批"}
_VERIFY_LABELS = {"en": "Result verification & cross-checking", "zh": "多维执行结果验收与核验"}
_COMPLETED_LABELS = {"en": "Final deliverable ready", "zh": "最终成果交付完成"}
_LANE_LABELS = {
    "clarify": {"en": "Clarification: {tool}", "zh": "交互澄清: {tool}"},
    "mcp": {"en": "External MCP call: {tool}", "zh": "MCP 外部调用: {tool}"},
    "skill": {"en": "Skill execution: {tool}", "zh": "技能执行: {tool}"},
    "sandbox_run": {"en": "Sandbox execution: {tool}", "zh": "沙箱执行: {tool}"},
    "tool": {"en": "Tool call: {tool}", "zh": "工具调用: {tool}"},
}


def _planning_label(lang: str) -> str:
    return _PLANNING_LABELS[lang]


class PhaseTransitionTracker:
    """Tracks and emits phase transition events across the 3 macro phases and 6 lanes."""

    def __init__(self, message_id: str | None = None, locale: str | None = None) -> None:
        self.message_id: str | None = message_id
        self.current_phase: str = "planning"
        self.current_phase_index: int = 1
        self.current_lane: str = "agent"
        self.current_node_id: int = 1
        self._lang = "zh" if (locale or "en").lower().startswith("zh") else "en"
        self.current_node_label: str = _planning_label(self._lang)
        self.phase_start_time: float = time.time()
        self._initial_emitted: bool = False

    def emit_initial_if_needed(self) -> dict[str, object] | None:
        """Emit initial planning phase transition if not already emitted."""
        if not self._initial_emitted:
            self._initial_emitted = True
            return self._build_transition_event(
                phase="planning",
                phase_index=1,
                lane="agent",
                node_id=1,
                node_label=_planning_label(self._lang),
            )
        return None

    def on_chunk(self, chunk: dict[str, object] | object) -> dict[str, object] | None:
        """Inspect an incoming chunk and determine whether a phase/lane transition occurred."""
        if not isinstance(chunk, dict):
            return None

        event_type = str(chunk.get("type", ""))
        if event_type == "phase_transition":
            return None

        # 1. Tool execution phase & lane routing
        if event_type == "tool_start":
            tool_name = str(chunk.get("tool_name") or chunk.get("name") or "")
            if not tool_name and isinstance(chunk.get("data"), dict):
                data_dict = chunk["data"]
                if isinstance(data_dict, dict):
                    tool_name = str(data_dict.get("tool_name") or data_dict.get("name") or "")

            lane, node_id, label = self._resolve_tool_lane_and_node(tool_name)
            return self._transition_to(
                phase="executing",
                phase_index=2,
                lane=lane,
                node_id=node_id,
                node_label=label,
            )

        # 2. Reasoning or model generation
        if event_type == "reasoning":
            if self.current_lane != "llm":
                phase = "executing" if self.current_phase_index >= 2 else "planning"
                phase_idx = self.current_phase_index
                node_id = 12 if phase_idx == 2 else 6
                label = (_LLM_EXEC_LABELS[self._lang] if phase_idx == 2 else _LLM_PLAN_LABELS[self._lang])
                return self._transition_to(
                    phase=phase,
                    phase_index=phase_idx,
                    lane="llm",
                    node_id=node_id,
                    node_label=label,
                )

        # 3. User approval / HITL intervention
        if event_type in ("approval_required", "clarification_required", "tool_approval_request"):
            return self._transition_to(
                phase="executing",
                phase_index=2,
                lane="user",
                node_id=14,
                node_label=_APPROVAL_LABELS[self._lang],
            )

        # 4. Verification and reflect gate
        if event_type in ("verification_verdict", "query_grounding_blocked") or (
            event_type == "tool_start" and "_completion_check" in str(chunk.get("name", ""))
        ):
            return self._transition_to(
                phase="verifying",
                phase_index=3,
                lane="agent",
                node_id=26,
                node_label=_VERIFY_LABELS[self._lang],
            )

        # 5. Completion delivery
        if event_type == "message_end":
            return self._transition_to(
                phase="completed",
                phase_index=3,
                lane="agent",
                node_id=30,
                node_label=_COMPLETED_LABELS[self._lang],
            )

        return None

    def _resolve_tool_lane_and_node(self, tool_name: str) -> tuple[str, int, str]:
        """Resolve active execution lane and production node from tool name."""
        lower_name = tool_name.lower()
        if any(marker in lower_name for marker in _USER_HITL_TOOLS):
            return "user", 14, _LANE_LABELS["clarify"][self._lang].format(tool=tool_name)
        if any(marker in lower_name for marker in _MCP_MARKERS):
            return "mcp", 15, _LANE_LABELS["mcp"][self._lang].format(tool=tool_name)
        if any(marker in lower_name for marker in _SKILL_MARKERS):
            return "skills", 13, _LANE_LABELS["skill"][self._lang].format(tool=tool_name)
        if any(marker in lower_name for marker in _SANDBOX_TOOLS):
            return "sandbox", 17, _LANE_LABELS["sandbox_run"][self._lang].format(tool=tool_name)
        return "sandbox", 16, _LANE_LABELS["tool"][self._lang].format(tool=tool_name)

    def _transition_to(
        self,
        phase: str,
        phase_index: int,
        lane: str,
        node_id: int,
        node_label: str,
    ) -> dict[str, object] | None:
        """Record transition and return event dictionary if state genuinely changed."""
        if (
            self.current_phase == phase
            and self.current_phase_index == phase_index
            and self.current_lane == lane
            and self.current_node_id == node_id
        ):
            return None

        now = time.time()
        duration_ms = max(0, int((now - self.phase_start_time) * 1000))
        self.phase_start_time = now

        self.current_phase = phase
        self.current_phase_index = phase_index
        self.current_lane = lane
        self.current_node_id = node_id
        self.current_node_label = node_label

        return self._build_transition_event(
            phase=phase,
            phase_index=phase_index,
            lane=lane,
            node_id=node_id,
            node_label=node_label,
            duration_ms=duration_ms,
        )

    def _build_transition_event(
        self,
        phase: str,
        phase_index: int,
        lane: str,
        node_id: int,
        node_label: str,
        duration_ms: int = 0,
    ) -> dict[str, object]:
        return {
            "type": "phase_transition",
            "messageId": self.message_id,
            "data": {
                "phase": phase,
                "phase_index": phase_index,
                "active_lane": lane,
                "node_id": node_id,
                "node_label": node_label,
                "duration_ms": duration_ms,
            },
        }
