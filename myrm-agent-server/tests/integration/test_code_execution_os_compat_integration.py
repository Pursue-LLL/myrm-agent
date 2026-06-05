"""Real code execution integration tests (no LLM mock).

Validates os_compat process-group and persistent-session paths used by
bash_code_execute_tool in production.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.code_execution.session.local_session import (
    LocalPersistentSession,
)
from myrm_agent_harness.toolkits.code_execution.session.persistent_session import (
    SessionConfig,
)
from myrm_agent_harness.utils import os_compat


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_persistent_session_python_multiply_real(tmp_path: Path) -> None:
    """Real bash session executes Python and returns exact product."""
    config = SessionConfig(
        session_id="os-compat-integ",
        work_dir=str(tmp_path),
        timeout=30,
        sandbox_mode="disable",
    )
    session = LocalPersistentSession(config)
    await session.start()
    try:
        result = await session.execute('python3 -c "print(898989 * 121212)"')
        assert result.success, result.stderr
        assert _digits("108968254668") in _digits(result.stdout)
    finally:
        await session.close()


@pytest.mark.integration
def test_os_compat_process_group_kwargs_on_host() -> None:
    """Host platform returns valid subprocess kwargs."""
    kwargs = os_compat.get_process_group_kwargs()
    if os_compat.IS_WIN:
        assert "creationflags" in kwargs
    else:
        assert kwargs.get("start_new_session") is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_os_compat_kill_process_group_no_crash() -> None:
    """kill_process_group on dead PID must not raise."""
    proc = await asyncio.create_subprocess_exec(
        "sleep",
        "60",
        **os_compat.get_process_group_kwargs(),  # type: ignore[arg-type]
    )
    pid = proc.pid
    assert pid is not None
    os_compat.kill_process_group(pid)
    await proc.wait()
    assert proc.returncode is not None
