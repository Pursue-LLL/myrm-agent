"""Architecture test: Conversation Recall repositories live in a dedicated subpackage."""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORIES_ROOT = _SERVER_ROOT / "app" / "database" / "repositories"
_CONVERSATION_RECALL_PACKAGE = _REPOSITORIES_ROOT / "conversation_recall"

_REQUIRED_MODULE_FILES = (
    "__init__.py",
    "_ARCH.md",
    "repo.py",
    "lookup_repo.py",
    "sql.py",
    "types.py",
)

_FORBIDDEN_LEGACY_FLAT_FILES = (
    "conversation_recall_repo.py",
    "conversation_recall_lookup_repo.py",
    "conversation_recall_sql.py",
    "conversation_recall_types.py",
)


@pytest.mark.architecture
def test_conversation_recall_subpackage_layout() -> None:
    assert _CONVERSATION_RECALL_PACKAGE.is_dir(), (
        f"Missing {_CONVERSATION_RECALL_PACKAGE}. "
        "See app/database/repositories/conversation_recall/_ARCH.md."
    )
    for filename in _REQUIRED_MODULE_FILES:
        path = _CONVERSATION_RECALL_PACKAGE / filename
        assert path.is_file(), f"Missing required conversation_recall module file: {path}"


@pytest.mark.architecture
@pytest.mark.parametrize("legacy_filename", _FORBIDDEN_LEGACY_FLAT_FILES)
def test_conversation_recall_legacy_flat_files_removed(legacy_filename: str) -> None:
    legacy_path = _REPOSITORIES_ROOT / legacy_filename
    assert not legacy_path.exists(), (
        f"Legacy flat conversation recall file must not reappear: {legacy_path}. "
        "Use app/database/repositories/conversation_recall/ instead."
    )


@pytest.mark.architecture
def test_conversation_recall_public_exports() -> None:
    from app.database.repositories.conversation_recall import (
        CONVERSATION_RECALL_SCHEMA_SQL,
        ConversationRecallLookupRepository,
        ConversationRecallRepository,
    )

    assert CONVERSATION_RECALL_SCHEMA_SQL
    assert ConversationRecallRepository is not None
    assert ConversationRecallLookupRepository is not None
