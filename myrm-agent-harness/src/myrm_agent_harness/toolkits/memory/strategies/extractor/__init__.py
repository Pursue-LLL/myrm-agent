"""记忆提取门面。

[OUTPUT]
MemoryExtractor / FeedbackSignal / ExtractionConfig / ExtractedMemory / ExtractionResult /
detect_feedback_signals / detect_correction_signals / detect_language /
extract_memories_from_conversation / extract_goal_learnings / _parse_response

[POS]
`myrm_agent_harness.toolkits.memory.strategies.extractor` 的唯一入口；实现按阶段拆在子模块。
"""

from myrm_agent_harness.toolkits.memory.strategies.extractor.models import (
    ConcreteMemory,
    ExtractedMemory,
    ExtractionConfig,
    ExtractionResult,
    LLMFunc,
)
from myrm_agent_harness.toolkits.memory.strategies.extractor.parse import _parse_response
from myrm_agent_harness.toolkits.memory.strategies.extractor.pipeline import (
    extract_goal_learnings,
    extract_memories_from_conversation,
)
from myrm_agent_harness.toolkits.memory.strategies.extractor.prompt import (
    _build_system_prompt,
    detect_language,
)
from myrm_agent_harness.toolkits.memory.strategies.extractor.runner import MemoryExtractor
from myrm_agent_harness.toolkits.memory.strategies.extractor.signals import (
    FeedbackSignal,
    detect_correction_signals,
    detect_feedback_signals,
)

__all__ = [
    "ConcreteMemory",
    "ExtractedMemory",
    "ExtractionConfig",
    "ExtractionResult",
    "FeedbackSignal",
    "LLMFunc",
    "MemoryExtractor",
    "_build_system_prompt",
    "_parse_response",
    "detect_correction_signals",
    "detect_feedback_signals",
    "detect_language",
    "extract_goal_learnings",
    "extract_memories_from_conversation",
]
