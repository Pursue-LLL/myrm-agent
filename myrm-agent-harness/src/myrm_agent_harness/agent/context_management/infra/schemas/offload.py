"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- ContextOffloadResult / ContextOffloadFailureKind / EvictedToolCall / 规范化函数

[POS]
`infra/schemas/` 的工具结果 offload 与驱逐类型。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

ContextOffloadFailureKind = Literal[
    "temporary_failure",
    "permission_denied",
    "quota_exceeded",
    "unsupported",
]


@dataclass(frozen=True, slots=True)
class ContextOffloadResult:
    """Result of offloading full context content before compression/pruning."""

    path: str = ""
    failure_kind: ContextOffloadFailureKind | None = None
    message: str = ""
    reused: bool = False
    original_bytes: int = 0
    stored_bytes: int = 0

    @property
    def succeeded(self) -> bool:
        return bool(self.path.strip()) and self.failure_kind is None

    @classmethod
    def success(
        cls,
        path: str,
        *,
        reused: bool = False,
        original_bytes: int = 0,
        stored_bytes: int = 0,
    ) -> ContextOffloadResult:
        return cls(
            path=path.strip(),
            reused=reused,
            original_bytes=max(original_bytes, 0),
            stored_bytes=max(stored_bytes, 0),
        )

    @classmethod
    def failure(
        cls,
        failure_kind: ContextOffloadFailureKind,
        message: str = "",
    ) -> ContextOffloadResult:
        return cls(failure_kind=failure_kind, message=message)


def normalize_context_offload_result(value: str | ContextOffloadResult) -> ContextOffloadResult:
    if isinstance(value, ContextOffloadResult):
        return value
    return ContextOffloadResult.success(value) if value.strip() else ContextOffloadResult.failure("temporary_failure")


@dataclass
class EvictedToolCall:
    """Evicted tool call data, containing original uncompressed content.

    Attributes:
        ai_msg: The AI message that initiated the tool call
        tool_msg: Tool response message (compressed reference, used only for metadata like name)
        original_content: Original tool output content before compression
    """

    ai_msg: BaseMessage
    tool_msg: BaseMessage
    original_content: str
