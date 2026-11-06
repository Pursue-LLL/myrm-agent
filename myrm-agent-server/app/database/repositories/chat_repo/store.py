"""[INPUT]
- .chats / .messages / .siblings / .routing (POS: repository mixins)

[OUTPUT]
- ChatRepository

[POS]
The chat repository: four stateless mixins composed into one class.
"""

from __future__ import annotations

from .chats import ChatsMixin
from .messages import MessagesMixin
from .routing import RoutingMixin
from .siblings import SiblingsMixin


class ChatRepository(ChatsMixin, MessagesMixin, SiblingsMixin, RoutingMixin):
    """Chat 领域的专有仓储类（Repository）。
    负责所有的 SQLAlchemy DB 交互，隔离上层服务（Service）与底层数据库结构的耦合。
    返回 Pydantic DTO (Domain Transfer Object) 以确保类型安全和解耦。"""
