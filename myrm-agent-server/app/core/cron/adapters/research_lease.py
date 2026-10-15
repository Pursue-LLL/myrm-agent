"""Read-only research lease for unattended cron runs.

[INPUT]
- myrm_agent_harness.core.security.readonly_research_sandbox::DEFAULT_READ_ONLY_TOOLS, ResearchModeEnum, get_readonly_research_sandbox_facade (POS: read-only lease registry the approval middleware enforces at tool-call time)
- myrm_agent_harness.core.security.tool_registry::resolve_permission_type (POS: tool name to capability permission token)
- myrm_agent_harness.toolkits.cron.types::CronJob (POS: cron job model)

[OUTPUT]
- is_read_only_job: whether every capability a job declares is one the lease permits
- grant_run_lease: put one run under a private read-only lease and return the key to release it with
- release_run_lease: revoke a run's lease and drop its overlay

[POS]
Decides which cron runs execute under the harness read-only research lease: jobs that declare nothing or only
read capabilities, and every run an untrusted sender started. The lease is keyed by the run's approval session, so
each leased run gets a private key; runs of one job never revoke each other's lease, and a stranger's run never
shares denial state with the owner's.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from typing import Protocol

from myrm_agent_harness.core.security.readonly_research_sandbox import (
    DEFAULT_READ_ONLY_TOOLS,
    ResearchModeEnum,
    get_readonly_research_sandbox_facade,
)
from myrm_agent_harness.core.security.tool_registry import resolve_permission_type
from myrm_agent_harness.toolkits.cron.types import CronJob

logger = logging.getLogger(__name__)

# Capability tokens (permission types) of the tools the lease allows. A job declaring anything else wants a tool
# the lease would deny, so it runs under its declared capabilities alone.
_LEASE_PERMISSIONS: frozenset[str] = frozenset(resolve_permission_type(tool) for tool in DEFAULT_READ_ONLY_TOOLS)

# Slack past the run timeout so the lease never lapses while the run is still being cancelled.
_LEASE_TTL_GRACE_SECONDS = 60.0


class _ApprovalKeyed(Protocol):
    approval_session_key: str | None


def is_read_only_job(required_capabilities: Iterable[str]) -> bool:
    """Whether a job declaring these capabilities (none included) never needs a tool outside the lease."""
    return frozenset(required_capabilities) <= _LEASE_PERMISSIONS


def grant_run_lease(agent: _ApprovalKeyed, job: CronJob, *, timeout_seconds: int, untrusted: bool) -> str | None:
    """Put the run under a read-only lease when its job is read-only or an untrusted sender started it.

    The lease is keyed by a private approval session key that is assigned to ``agent``; the ``cron:`` prefix keeps
    the unattended approval behaviour keyed on it. Returns that key for ``release_run_lease``, or ``None`` when
    the run goes without a lease and keeps ``agent``'s key.
    """
    if not untrusted and not is_read_only_job(job.required_capabilities):
        return None
    session_key = f"cron:{job.id}:{uuid.uuid4().hex[:12]}"
    get_readonly_research_sandbox_facade().grant_research_lease(
        session_id=session_key,
        research_mode=ResearchModeEnum.AUTONOMOUS_RESEARCH,
        ttl_seconds=float(timeout_seconds) + _LEASE_TTL_GRACE_SECONDS,
    )
    agent.approval_session_key = session_key
    return session_key


def release_run_lease(session_key: str) -> None:
    """Revoke a run's lease and drop its overlay; best effort, so cleanup never fails the run."""
    try:
        facade = get_readonly_research_sandbox_facade()
        facade.revoke_lease(session_key)
        facade.purge_ephemeral_overlay(session_key)
    except Exception as exc:
        logger.debug("Read-only research lease cleanup ignored: %s", exc)
