"""[INPUT]
- .writes / .search / .queries (POS: repository mixins)

[OUTPUT]
- ConversationRecallRepository

[POS]
The Conversation Recall repository: three stateless mixins composed into one class.
"""

from __future__ import annotations

from .queries import QueriesMixin
from .search import SearchMixin
from .writes import WritesMixin


class ConversationRecallRepository(WritesMixin, SearchMixin, QueriesMixin):
    """Read/write repository for the conversation recall index."""
