"""Myrm service lifecycle guard for cron job mutations.

Blocks cron jobs whose prompt, shell command, pre_condition_script, or shell acceptance criteria
contain Myrm service restart/stop patterns, preventing SIGTERM-respawn loops when the job fires.

[INPUT]
- (none — stateless regex matcher)

[OUTPUT]
- contains_myrm_lifecycle_command: Check if text contains lifecycle commands
- assert_cron_job_lifecycle_safe: Reject cron specs with lifecycle commands (prompt, command, pre_condition_script, shell acceptance criteria)

[POS]
Cron lifecycle guard — prevents restart/stop loops from user-scheduled jobs.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence

# A verb and the service it targets must sit on one line at most this far apart. A real command line is far
# shorter, and an unbounded gap makes the scan quadratic on long repeated text.
_MAX_VERB_TO_SERVICE_GAP = 200
_GAP = rf"[^\n]{{0,{_MAX_VERB_TO_SERVICE_GAP}}}"

_MYRM_LIFECYCLE_PATTERN = re.compile(
    r"(?i)"
    r"(?:\bmyrm(?:-dev)?\s+(?:restart|stop)\b)"
    rf"|(?:launchctl\s+(?:kickstart|unload|load|bootout|bootstrap|stop|restart)\b{_GAP}\bmyrm\b)"
    rf"|(?:systemctl\s+(?:-\S+\s+)*(?:restart|stop|start)\b{_GAP}\bmyrm-agent\b)"
    rf"|(?:\b(?:p?kill|killall|taskkill|stop-process)\b{_GAP}\bmyrm-agent\b)"
)

# Acceptance criteria of this type run their ``command`` through the shell after a direct-mode job run.
_SHELL_CRITERION_TYPE = "shell"


def contains_myrm_lifecycle_command(text: str) -> bool:
    """Return True if *text* contains a Myrm service lifecycle command pattern."""
    if not text:
        return False
    return bool(_MYRM_LIFECYCLE_PATTERN.search(text))


def _shell_criterion_commands(criteria: Sequence[Mapping[str, object]]) -> Iterator[str]:
    """Yield the command each shell criterion executes (the verifier runs ``str(command)``)."""
    for criterion in criteria:
        if criterion.get("type") == _SHELL_CRITERION_TYPE and "command" in criterion:
            yield str(criterion["command"])


def assert_cron_job_lifecycle_safe(
    *,
    prompt: str | None,
    command: str | None,
    pre_condition_script: str | None = None,
    acceptance_criteria: Sequence[Mapping[str, object]] = (),
) -> None:
    """Reject cron specs that would restart or stop the Myrm service."""
    checked_texts = (
        ("prompt", prompt),
        ("command", command),
        ("pre_condition_script", pre_condition_script),
        *(("acceptance criterion command", text) for text in _shell_criterion_commands(acceptance_criteria)),
    )
    for field, text in checked_texts:
        if text and contains_myrm_lifecycle_command(text):
            raise ValueError(
                f"Cron {field} must not contain Myrm service lifecycle commands "
                "(restart/stop) — this would cause a restart loop when the job fires."
            )
