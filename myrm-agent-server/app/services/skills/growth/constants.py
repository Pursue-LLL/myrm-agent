"""
[INPUT]
- (none)

[OUTPUT]
- GROWTH_ACTION_TYPES: action types stored as growth drafts in ApprovalRecord
- LEDGER_GROWTH_ACTION_TYPES: subset projected into the experience ledger
- is_background_growth_approval(): classify inbox-only growth approvals

[POS]
Single source of truth for skill-growth approval action_type strings shared by
drafts API queries and approval registry global-recovery filtering.
"""

GROWTH_ACTION_TYPES: tuple[str, ...] = ("skill_draft", "skill_patch", "semantic_memory")

LEDGER_GROWTH_ACTION_TYPES: tuple[str, ...] = ("skill_draft", "skill_patch")


def is_background_growth_approval(action_type: str, thread_id: str | None) -> bool:
    """Background growth drafts use /skills/drafts inbox, not global /approvals recovery."""
    return action_type in GROWTH_ACTION_TYPES and not thread_id
