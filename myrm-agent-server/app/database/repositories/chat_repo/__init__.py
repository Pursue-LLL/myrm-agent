"""Chat repository.

[INPUT]
- .store / .siblings (POS: composed repository + sibling DTO)

[OUTPUT]
- ChatRepository, SiblingDetail

[POS]
Aggregate exit of the chat repository package; import path unchanged.
"""

from __future__ import annotations

from .siblings import SiblingDetail
from .store import ChatRepository

__all__ = ["ChatRepository", "SiblingDetail"]
