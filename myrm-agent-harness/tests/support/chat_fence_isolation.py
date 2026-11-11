"""Keep the chats a test closed away from the next test (a pytest plugin).

[INPUT]
- toolkits.memory.strategies.chat_fence::clear_closed_chats (POS: forget every chat the fence refuses writes for)

[OUTPUT]
- _isolate_closed_chats: autouse fixture; every test starts, and ends, with no chat closed

[POS]
Registered from ``tests/conftest.py`` (``pytest_plugins``). Purging a chat closes it in the process-wide fence for
fifteen minutes, so a test that purges ``chat-a`` would make a later test that writes a memory of ``chat-a`` for the
same user fail, depending on which test the worker ran first.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _isolate_closed_chats() -> Iterator[None]:
    from myrm_agent_harness.toolkits.memory.strategies.chat_fence import clear_closed_chats

    clear_closed_chats()
    yield
    clear_closed_chats()
