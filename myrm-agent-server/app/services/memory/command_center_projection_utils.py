"""Memory command-center projection helpers.

[INPUT]
app.schemas.memory.command_center::MemoryCommandEvalMetric (POS: 记忆指挥中心 API Schema 层)

[OUTPUT]
ReplayPhase, WaterfallPhase, WATERFALL_PHASES and projection helper functions for command-center views.

[POS]
个人大脑指挥中心投影辅助层。集中维护阶段映射、状态计算、预览与轻量数值解析。
"""

from __future__ import annotations

from typing import Literal

from app.schemas.memory.command_center import MemoryCommandEvalMetric

ReplayPhase = Literal["observe", "govern", "write", "index", "recall", "inject", "verify"]
WaterfallPhase = Literal["observe", "scan", "propose", "approve", "write", "index", "recall", "inject", "cite", "verify"]
WaterfallStatus = Literal["ready", "active", "warning", "missing"]

WATERFALL_PHASES: tuple[WaterfallPhase, ...] = (
    "observe",
    "scan",
    "propose",
    "approve",
    "write",
    "index",
    "recall",
    "inject",
    "cite",
    "verify",
)


def preview_content(content: str, *, limit: int = 160) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}..."


def optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def dict_int(value: object, key: str) -> int:
    if not isinstance(value, dict):
        return 0
    raw = value.get(key)
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return max(raw, 0)
    if isinstance(raw, float):
        return max(int(raw), 0)
    return 0


def event_phase(kind: str) -> ReplayPhase:
    if kind in {"observe", "extract"}:
        return "observe"
    if kind in {"propose", "approve", "reject"}:
        return "govern"
    if kind in {"write", "correct", "forget", "import_memory", "export_memory"}:
        return "write"
    if kind == "index":
        return "index"
    if kind in {"recall", "cite"}:
        return "recall"
    if kind == "inject":
        return "inject"
    return "verify"


def waterfall_phase(kind: str) -> WaterfallPhase:
    mapping: dict[str, WaterfallPhase] = {
        "observe": "observe",
        "extract": "scan",
        "propose": "propose",
        "approve": "approve",
        "reject": "approve",
        "write": "write",
        "correct": "write",
        "forget": "write",
        "index": "index",
        "recall": "recall",
        "cite": "cite",
        "inject": "inject",
        "health_check": "verify",
    }
    return mapping.get(kind, "verify")


def waterfall_status(phase: WaterfallPhase, count: int) -> WaterfallStatus:
    if count > 0:
        return "active"
    if phase in {"scan", "index", "inject"}:
        return "missing"
    return "ready"


def waterfall_description(phase: WaterfallPhase, count: int) -> str:
    if count:
        return f"{count} recorded events feed this phase."
    descriptions: dict[WaterfallPhase, str] = {
        "scan": "No explicit scan events are recorded yet.",
        "index": "No explicit index events are recorded yet.",
        "inject": "No explicit injection events are recorded yet.",
    }
    return descriptions.get(phase, "Phase is available when matching events are recorded.")


def eval_metric(metric_id: str, partial: bool, ready: bool, evidence: str) -> MemoryCommandEvalMetric:
    status = "ready" if ready else "partial" if partial else "missing"
    score = 100 if ready else 60 if partial else 0
    return MemoryCommandEvalMetric(id=metric_id, label=metric_id, status=status, score=score, evidence=evidence)
