"""[OUTPUT]
- logger / _DTO_COMPUTED_FIELDS / _INCOGNITO_BLANKED_FIELDS

[POS]
Shared constants of the chat repository.
"""

from __future__ import annotations

import logging

from sqlalchemy import and_, func
from sqlalchemy.sql.elements import ColumnElement

from app.database.dto import MessageDTO
from app.database.models import Message
from app.database.models.chat import SYSTEM_NOTICE_EXTRA_KEYS

logger = logging.getLogger(__name__)

_DTO_COMPUTED_FIELDS: set[str] = {"sibling_count", "sibling_index"}

_INCOGNITO_BLANKED_FIELDS: frozenset[str] = frozenset({"title", "first_message", "last_message"})


def _answers_of_turn(chat_id: str, last_user: MessageDTO) -> ColumnElement[bool]:
    """Answers of the turn *last_user* opened: every assistant message ordered after it, active or not.

    System notices (`SYSTEM_NOTICE_EXTRA_KEYS` set to true) are appended by the server rather than generated for the
    turn, so they are neither retried nor counted as versions of its answer. SQLite's `json_extract` yields 1 for a
    JSON true and NULL for an absent key or a NULL column, so `IS NOT 1` keeps every row that is not a notice.
    """
    return and_(
        Message.chat_id == chat_id,
        Message.role == "assistant",
        (Message.created_at > last_user.created_at)
        | ((Message.created_at == last_user.created_at) & (Message.id > last_user.id)),
        *(func.json_extract(Message.extra_data, f"$.{key}").is_not(1) for key in SYSTEM_NOTICE_EXTRA_KEYS),
    )
