"""The children a caller is blocked on, whose results reach that caller instead of waking the parent.

[INPUT]
- None (stdlib only)

[OUTPUT]
- AwaitedChildren: a counted set of task ids with a ``held`` scope; ``task_id in awaited`` tells the manager that a
  settled child's result already has a reader

[POS]
Ownership of a settled child's result. The parent's wakeup exists to deliver a result nobody is waiting for; a caller
blocked in ``spawn_child(wait=True)`` or ``wait_children`` receives the result itself, so waking the parent as well
would repeat it. The hold ends when the caller stops waiting, so a child that outlives a wait timeout still wakes the
parent when it settles.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import contextmanager


class AwaitedChildren:
    """Task ids some caller is blocked on right now; an id counts once per blocked caller."""

    __slots__ = ("_holds",)

    def __init__(self) -> None:
        self._holds: Counter[str] = Counter()

    @contextmanager
    def held(self, task_ids: Iterable[str]) -> Iterator[None]:
        """Mark ``task_ids`` as awaited for the block; every exit, including a cancelled wait, releases them."""
        ids = tuple(task_ids)
        self._holds.update(ids)
        try:
            yield
        finally:
            for task_id in ids:
                if self._holds[task_id] > 1:
                    self._holds[task_id] -= 1
                else:
                    del self._holds[task_id]

    def __contains__(self, task_id: str) -> bool:
        return task_id in self._holds
