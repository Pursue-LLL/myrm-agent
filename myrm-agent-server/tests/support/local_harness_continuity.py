"""Load local myrm-agent-harness source for continuity integration tests."""

from __future__ import annotations

import sys
from pathlib import Path

_LOCAL_HARNESS_SRC = (
    Path(__file__).resolve().parents[4] / "myrm-agent-harness" / "src"
)


def ensure_local_harness_on_path() -> None:
    harness_src = str(_LOCAL_HARNESS_SRC)
    if harness_src not in sys.path:
        sys.path.insert(0, harness_src)


def patch_session_continuity_sync(monkeypatch) -> None:
    """Point server continuity adapter at in-repo harness implementation."""
    ensure_local_harness_on_path()
    module_name = "myrm_agent_harness.runtime.context.session_continuity"
    sys.modules.pop(module_name, None)
    from myrm_agent_harness.runtime.context import session_continuity as local_sc

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.sync_checkpoint_messages",
        local_sc.sync_checkpoint_messages,
    )
    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.ContinuitySyncError",
        local_sc.ContinuitySyncError,
    )
