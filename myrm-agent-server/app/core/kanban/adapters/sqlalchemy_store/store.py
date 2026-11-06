"""[INPUT]
- .boards / .tasks / .dependencies / .plan / .execution / .runs / .events (POS: store mixins)

[OUTPUT]
- SqlAlchemyKanbanStore

[POS]
The kanban store: behavior composed from seven mixins; it holds no instance state, every method opens its own session.
"""

from __future__ import annotations

from .boards import BoardsMixin
from .dependencies import DependenciesMixin
from .events import EventsMixin
from .execution import ExecutionMixin
from .plan import PlanMixin
from .runs import RunsMixin
from .tasks import TasksMixin


class SqlAlchemyKanbanStore(
    BoardsMixin,
    TasksMixin,
    DependenciesMixin,
    PlanMixin,
    ExecutionMixin,
    RunsMixin,
    EventsMixin,
):
    """KanbanStore backed by SQLAlchemy + app.database models."""
