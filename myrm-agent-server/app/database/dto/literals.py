"""[INPUT]
- pydantic / typing (POS: model primitives)

[OUTPUT]
- PersonalityStyleLiteral, MemoryDecayProfileLiteral, MemoryExtractionPresetLiteral, PromptModeLiteral, SecurityPresetLiteral, WorkspacePolicyLiteral, AgentTypeLiteral, SessionResetModeLiteral, normalize_workspace_policy

[POS]
Data transfer objects: stored value vocabularies (Literal aliases) and the workspace-policy normalizer.
"""

from __future__ import annotations

from typing import Literal

PersonalityStyleLiteral = Literal[
    # 实用型
    "professional",
    "friendly",
    "concise",
    "detailed",
    "humorous",
    "academic",
    "creative",
    "socratic",
    # 趣味型
    "pirate",
    "shakespeare",
    "noir",
    "kawaii",
    "catgirl",
    "hype",
    "uwu",
    "surfer",
    "wenyan",
]


MemoryDecayProfileLiteral = Literal["permanent", "normal", "fast"]


MemoryExtractionPresetLiteral = Literal["none", "auto", "persona", "work_assistant", "research"]


PromptModeLiteral = Literal["full", "lean", "naked", "search"]


SecurityPresetLiteral = Literal["hitl", "accept_edits", "explore"]


WorkspacePolicyLiteral = Literal["INHERIT_REQUESTER", "READ_ONLY_SANDBOX"]


AgentTypeLiteral = Literal["individual", "team"]


SessionResetModeLiteral = Literal["persistent", "daily", "idle"]


def normalize_workspace_policy(stored: object) -> WorkspacePolicyLiteral:
    """Read a stored policy: anything but READ_ONLY_SANDBOX (e.g. the retired ISOLATED_COPY) inherits."""
    return "READ_ONLY_SANDBOX" if stored == "READ_ONLY_SANDBOX" else "INHERIT_REQUESTER"
