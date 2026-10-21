"""
[POS] Kanban persistence adapters — ORM mapping, SQLAlchemy store, setup.
"""

from .sqlalchemy_store import SqlAlchemyKanbanStore

__all__ = ["SqlAlchemyKanbanStore"]
