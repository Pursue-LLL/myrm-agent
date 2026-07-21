"""Myrm service lifecycle guard for cron job mutations.

Blocks cron jobs whose prompt, shell command, or pre_condition_script contains
Myrm service restart/stop patterns, preventing SIGTERM-respawn loops when the
job fires.

[INPUT]
- (none — stateless regex matcher)

[OUTPUT]
- contains_myrm_lifecycle_command: Check if text contains lifecycle commands
- assert_cron_job_lifecycle_safe: Reject cron specs with lifecycle commands (prompt, command, pre_condition_script)

[POS]
Cron lifecycle guard — prevents restart/stop loops from user-scheduled jobs.
"""

from __future__ import annotations

import re

_MYRM_LIFECYCLE_PATTERN = re.compile(
    r"(?i)"
    r"(?:\./myrm\s+(?:restart|stop)\b)"
    r"|(?:\bmyrm\s+(?:restart|stop)\b)"
    r"|(?:launchctl\s+(?:kickstart|unload|load|stop|restart)\b[^\n]*\bmyrm\b)"
    r"|(?:systemctl\s+(?:-\S+\s+)*(?:restart|stop|start)\b[^\n]*\bmyrm-agent\b)"
    r"|(?:p?kill\b[^\n]*\bmyrm-agent(?:-server|-frontend)?\b)"
)


def contains_myrm_lifecycle_command(text: str) -> bool:
    """Return True if *text* contains a Myrm service lifecycle command pattern."""
    if not text:
        return False
    return bool(_MYRM_LIFECYCLE_PATTERN.search(text))


def assert_cron_job_lifecycle_safe(
    *,
    prompt: str | None,
    command: str | None,
    pre_condition_script: str | None = None,
) -> None:
    """Reject cron specs that would restart or stop the Myrm service."""
    if prompt and contains_myrm_lifecycle_command(prompt):
        raise ValueError(
            "Cron prompt must not contain Myrm service lifecycle commands "
            "(restart/stop) — this would cause a restart loop when the job fires."
        )
    if command and contains_myrm_lifecycle_command(command):
        raise ValueError(
            "Cron command must not contain Myrm service lifecycle commands "
            "(restart/stop) — this would cause a restart loop when the job fires."
        )
    if pre_condition_script and contains_myrm_lifecycle_command(pre_condition_script):
        raise ValueError(
            "Cron pre_condition_script must not contain Myrm service lifecycle commands "
            "(restart/stop) — this would cause a restart loop when the job fires."
        )
