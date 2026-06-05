"""Smoke test: verify the blockbuster gate catches blocking IO and opt-out works.

Tests in this directory are automatically gated by the blockbuster
hookwrapper in conftest.py. The gate only fires for callers whose stack
includes ``app.*``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from blockbuster import BlockingError


async def test_blockbuster_gate_catches_server_blocking_io(tmp_path: Path) -> None:
    """Verify that the gate catches blocking IO from server code.

    Calls a real server utility that performs synchronous ``Path.mkdir``.
    """
    from app.config.migrator import _get_config_version_path

    with pytest.raises(BlockingError):
        _get_config_version_path(tmp_path / "gate_test_dir")


@pytest.mark.allow_blocking_io
async def test_allow_blocking_io_marker_opts_out(tmp_path: Path) -> None:
    """Tests marked allow_blocking_io bypass the gate."""
    from app.config.migrator import _get_config_version_path

    result = _get_config_version_path(tmp_path / "opt_out_dir")
    assert result.parent.exists()
