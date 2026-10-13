"""Skill replace orchestration (Skill Change Contract).

[INPUT]
- .service::assert_replace_allowed (POS: Server-layer SSOT for market/prebuilt/install-overwrite replace safety)

[OUTPUT]
- SkillReplaceBlockedError, assert_replace_allowed, create_replace_snapshot, install_result_from_blocked, record_successful_replace: replace-safety gate and undo-snapshot facade

[POS]
Package facade of the replace-safety service used by skill install, update and overwrite paths.
"""

from .service import (
    SkillReplaceBlockedError,
    assert_replace_allowed,
    create_replace_snapshot,
    install_result_from_blocked,
    record_successful_replace,
)

__all__ = [
    "SkillReplaceBlockedError",
    "assert_replace_allowed",
    "create_replace_snapshot",
    "install_result_from_blocked",
    "record_successful_replace",
]
