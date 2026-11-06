"""[INPUT]
- .reads / .create / .update / .mapping (POS: repository mixins)

[OUTPUT]
- AgentRepository

[POS]
The agent profile repository: four stateless mixins composed into one class.
"""

from __future__ import annotations

from .create import CreateMixin
from .mapping import MappingMixin
from .reads import ReadsMixin
from .update import UpdateMixin


class AgentRepository(ReadsMixin, CreateMixin, UpdateMixin, MappingMixin):
    """Agent 领域的专有仓储类（Repository）。
    负责所有的 SQLAlchemy DB 交互，隔离上层服务（Service）与底层数据库结构的耦合。
    并负责将底层 Agent 模型转换为业务层的 AgentProfile 数据类。"""
