"""AI Agent 模块 — 延迟加载避免启动时导入重型依赖（litellm/langchain）"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agents import (
        AgentFactory,
        BaseAgentParams,
        GeneralAgentParams,
        ImageGenerationParams,
        TTSParams,
        VideoGenerationParams,
    )
    from .general_agent import GeneralAgent

def __getattr__(name: str) -> object:
    if name in (
        "AgentFactory",
        "BaseAgentParams",
        "GeneralAgentParams",
        "ImageGenerationParams",
        "VideoGenerationParams",
        "TTSParams",
    ):
        from .agents import (
            AgentFactory,
            BaseAgentParams,
            GeneralAgentParams,
            ImageGenerationParams,
            TTSParams,
            VideoGenerationParams,
        )

        _exports = {
            "AgentFactory": AgentFactory,
            "BaseAgentParams": BaseAgentParams,
            "GeneralAgentParams": GeneralAgentParams,
            "ImageGenerationParams": ImageGenerationParams,
            "VideoGenerationParams": VideoGenerationParams,
            "TTSParams": TTSParams,
        }
        return _exports[name]
    if name == "GeneralAgent":
        from .general_agent import GeneralAgent

        return GeneralAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AgentFactory",
    "BaseAgentParams",
    "GeneralAgentParams",
    "ImageGenerationParams",
    "VideoGenerationParams",
    "TTSParams",
    "GeneralAgent",
]
