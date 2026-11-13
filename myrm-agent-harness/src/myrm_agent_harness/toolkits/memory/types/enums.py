"""[INPUT]
- （标准库 enum）

[OUTPUT]
- 记忆分类、层级、状态与冲突处置枚举

[POS]
`memory/types/` 的枚举定义；不依赖任何模型或后端。
"""

from __future__ import annotations

from enum import StrEnum


class MemoryType(StrEnum):
    PROFILE = "profile"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    CONVERSATION = "conversation"
    PROCEDURAL = "procedural"
    CLAIM = "claim"
    TASK_DIGEST = "task_digest"
    INTEGRATION = "integration"


class RuleSource(StrEnum):
    USER_EXTRACTED = "user_extracted"
    AGENT_SELF = "agent_self"
    USER_EXPLICIT = "user_explicit"


class MemoryTier(StrEnum):
    L1 = "l1"
    L2 = "l2"
    L3 = "l3"


class DigestKind(StrEnum):
    TASK = "task"


class EvaporationState(StrEnum):
    PENDING = "pending"
    EVAPORATED = "evaporated"


class ClaimGraphState(StrEnum):
    PENDING = "pending"
    COMPILED = "compiled"


class ClaimConflictState(StrEnum):
    NONE = "none"
    CONFLICTED = "conflicted"


class ConflictResolution(StrEnum):
    """Resolution action for a detected memory contradiction.

    Used by the consolidation conflict callback to communicate
    the user's decision back to the framework.
    """

    KEEP_OLD = "keep_old"
    KEEP_NEW = "keep_new"
    MERGE = "merge"
    DISCARD_BOTH = "discard_both"
    PENDING = "pending"


class ToolRulePriority(StrEnum):
    """Compression resistance level for procedural rules.

    CRITICAL rules are excluded from TTL archiving (see
    ``maintenance_rule_forgetting``), and AGENT_SELF rules are downgraded to
    HIGH if they try to claim it (see ``write_service``). HIGH marks rules the
    extractor judged important and is the ceiling for agent-written rules.
    The level does not decide what the prompt budget keeps: every rule shares
    the stable-layer budget, and trimming drops rules from the end of the list.
    A user-endorsed rule (``is_user_locked``) is listed first, and a rule
    worded as a prohibition is pinned against the cut (see
    ``memory_context_format``).
    """

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"


class MemoryStatus(StrEnum):
    """Unified lifecycle status for all memory types."""

    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class PendingResolutionAction(StrEnum):
    """How an approved pending memory is applied to storage.

    ``STORE`` persists the candidate as a new memory (default, non-destructive).
    ``CORRECT`` demotes the targeted memory and stores the candidate as its linked
    correction. ``DELETE`` retires the targeted memory that is now factually wrong
    by archiving it (restorable until the archive retention purge).
    """

    STORE = "store"
    CORRECT = "correct"
    DELETE = "delete"
