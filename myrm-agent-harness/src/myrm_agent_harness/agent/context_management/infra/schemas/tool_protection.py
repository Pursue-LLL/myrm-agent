"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- ToolProtectionConfig / ToolPruneMode / 内置保护工具集合

[POS]
`infra/schemas/` 的工具保护与裁剪白名单配置。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    pass

# Minimum compression savings threshold (Prompt Cache protection).
# See CONTEXT_ENGINEERING.md §5.2.
# Assumes T_prefix=30k, T_cleared > T_prefix * (1-P), at 90% discount: 30k * 0.1 = 3k.
# 3000 tokens balances cache protection without being overly conservative.

BUILTIN_FILTER_PROTECTED_TOOLS: frozenset[str] = frozenset(
    {
        "skill_select_tool",
        "todo_write",
        "file_read_tool",
    }
)

BUILTIN_ACTIVE_PRUNE_NEVER_TOOLS: frozenset[str] = frozenset(
    {
        "skill_select_tool",
        "todo_write",
    }
)

BUILTIN_PROTECTED_TOOLS: frozenset[str] = BUILTIN_FILTER_PROTECTED_TOOLS

DEFAULT_BUSINESS_PROTECTED_TOOLS: set[str] = {
    "memory_search",
}

DEFAULT_SOFT_ONLY_TOOLS: set[str] = set()

ToolPruneMode = Literal["allow", "soft_only", "protect"]

@dataclass
class ToolProtectionConfig:
    """Tool protection configuration.

    Architecture: built-in + business tool protection.
    - Filter-protected: skill_select, todo_write, file_read (no UECD re-spill / read loop)
    - Active-prune-never: skill_select, todo_write (never archive placeholders)
    - Business: application-level tools (memory_search, etc.) are user-configurable
    - Soft-only: tools that can be trimmed but should not be fully archived

    Cache-TTL pruning uses prune_mode(): protected tools are never touched,
    soft-only tools can retain visible anchors, and the rest may be archived.
    """

    business_protected: set[str] = field(default_factory=lambda: DEFAULT_BUSINESS_PROTECTED_TOOLS.copy())
    soft_only_tools: set[str] = field(default_factory=lambda: DEFAULT_SOFT_ONLY_TOOLS.copy())
    enable_protection: bool = True

    def is_filter_protected(self, tool_name: str) -> bool:
        if not self.enable_protection:
            return False
        return tool_name in BUILTIN_FILTER_PROTECTED_TOOLS or tool_name in self.business_protected

    def is_active_prune_never(self, tool_name: str) -> bool:
        if not self.enable_protection:
            return False
        return tool_name in BUILTIN_ACTIVE_PRUNE_NEVER_TOOLS or tool_name in self.business_protected

    def is_protected(self, tool_name: str) -> bool:
        return self.is_filter_protected(tool_name)

    def get_all_protected(self) -> set[str]:
        return set(BUILTIN_PROTECTED_TOOLS) | self.business_protected

    def prune_mode(self, tool_name: str) -> ToolPruneMode:
        if self.is_protected(tool_name):
            return "protect"
        if self.enable_protection and tool_name in self.soft_only_tools:
            return "soft_only"
        return "allow"

    def add_business_protection(self, tool_name: str) -> None:
        self.business_protected.add(tool_name)

    def remove_business_protection(self, tool_name: str) -> None:
        self.business_protected.discard(tool_name)

    @classmethod
    def default(cls) -> ToolProtectionConfig:
        return cls()

    @classmethod
    def builtin_only(cls) -> ToolProtectionConfig:
        return cls(business_protected=set())

    @classmethod
    def disabled(cls) -> ToolProtectionConfig:
        return cls(business_protected=set(), soft_only_tools=set(), enable_protection=False)

TOOL_PROTECTION_CONFIG = ToolProtectionConfig.default()
