"""Deploy-mode gates for external_cli (local CLI delegation).

[INPUT] app.config.deploy_mode::is_local_mode (POS: LOCAL/TAURI vs SANDBOX deploy gate)
[OUTPUT] is_external_cli_deploy_supported: whether external_cli may stay enabled for current deploy
[POS] Product deploy gate for delegate_to_agent — cloud sandboxes cannot spawn host CLI processes.
"""

from __future__ import annotations

from app.config.deploy_mode import is_local_mode


def is_external_cli_deploy_supported() -> bool:
    """Whether this deployment can run external CLI delegation (local or Tauri only)."""
    return is_local_mode()


__all__ = [
    "is_external_cli_deploy_supported",
]
