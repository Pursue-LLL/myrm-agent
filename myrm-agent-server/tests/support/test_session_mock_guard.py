"""A module first imported under the DB-session patches keeps the mock unless the guard sweeps it.

The unguarded case reproduces the leak that made later tests hit a database whose tables were already dropped
(``no such table: user_configs``); the guarded case proves ``restore_leaked_session_mocks`` rebinds the module.
"""

from __future__ import annotations

import importlib
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.support.session_mock_guard import restore_leaked_session_mocks

_CONSUMER_SOURCE = "from app.database.connection import get_session\nfrom app.platform_utils import get_session_factory\n"


@pytest.mark.parametrize(
    ("use_guard", "module_name"),
    [
        pytest.param(False, "_session_consumer_unguarded", id="unguarded-leaks"),
        pytest.param(True, "_session_consumer_guarded", id="guarded-restores"),
    ],
)
def test_module_first_imported_under_patch_keeps_mock_unless_guarded(
    use_guard: bool,
    module_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.platform_utils as platform_utils
    from app.database import connection

    real_get_session = connection.get_session
    real_get_session_factory = platform_utils.get_session_factory

    async def mock_get_session() -> None:
        raise AssertionError("never called: identity only")

    def mock_get_session_factory() -> None:
        raise AssertionError("never called: identity only")

    (tmp_path / f"{module_name}.py").write_text(_CONSUMER_SOURCE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        with ExitStack() as stack:
            if use_guard:
                stack.enter_context(restore_leaked_session_mocks(mock_get_session, mock_get_session_factory))
            stack.enter_context(patch("app.database.connection.get_session", mock_get_session))
            stack.enter_context(patch("app.platform_utils.get_session_factory", mock_get_session_factory))

            consumer = importlib.import_module(module_name)
            assert consumer.get_session is mock_get_session
            assert consumer.get_session_factory is mock_get_session_factory

        assert connection.get_session is real_get_session
        assert platform_utils.get_session_factory is real_get_session_factory
        if use_guard:
            assert consumer.get_session is real_get_session
            assert consumer.get_session_factory is real_get_session_factory
        else:
            assert consumer.get_session is mock_get_session
            assert consumer.get_session_factory is mock_get_session_factory
    finally:
        sys.modules.pop(module_name, None)
