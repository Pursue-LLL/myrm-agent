"""Keep a per-test DB session mock from outliving its fixture.

[INPUT]
- sys.modules (POS: every module global that may have bound the mock)
- app.database.connection.get_session / app.platform_utils.get_session_factory (POS: the real providers)

[OUTPUT]
- restore_leaked_session_mocks(): context manager that rebinds module globals still holding the per-test mocks

[POS]
Listed first in the ``with (...)`` of the session-patching fixtures in tests/api/{agent,skills,companion,
notifications,approvals}/conftest.py, so it exits after ``patch`` has restored the attributes it names.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager


@contextmanager
def restore_leaked_session_mocks(
    mock_get_session: Callable[..., object],
    mock_get_session_factory: Callable[..., object],
) -> Iterator[None]:
    """Undo mock capture by modules first imported while the session providers are patched.

    ``patch`` only restores the attributes it names. A module imported for the first time during a test runs
    ``from app.database.connection import get_session`` against the patched attribute and keeps the mock for the
    rest of the process, so every later test talks to a database whose tables were already dropped. List this guard
    before the ``patch`` calls: it then exits last and sweeps after ``patch`` has put the real callables back.
    """
    import app.platform_utils as platform_utils
    from app.database import connection

    replacements: dict[int, Callable[..., object]] = {
        id(mock_get_session): connection.get_session,
        id(mock_get_session_factory): platform_utils.get_session_factory,
    }
    try:
        yield
    finally:
        for module in tuple(sys.modules.values()):
            namespace = getattr(module, "__dict__", None)
            if not isinstance(namespace, dict):
                continue
            for attr, value in tuple(namespace.items()):
                replacement = replacements.get(id(value))
                if replacement is not None:
                    namespace[attr] = replacement
