"""The persistent bash shells a local executor keeps, and what the directories granted beside the workspace mean to them.

A shell's OS sandbox is fixed when it starts, so a shell is kept per run identity, workspace mode and set of granted
directories: when the grants change the next command starts a shell under the new sandbox and the old one is closed.
A command may name a granted directory only when an OS sandbox is there to hold it to the grant, because the command
validator reads paths, not read from write.

[INPUT]
- core.context_vars::standing_access_roots (POS: The directories granted beside the workspace that outlast one call)
- core.security.types::AccessRoot (POS: A granted directory)
- sandbox::detect_sandbox_provider (POS: Whether an OS sandbox runs commands)
- sandbox.policy_bridge::sandbox_grant_roots (POS: The granted roots the sandbox can honour)
- session::LocalPersistentSession, SessionConfig (POS: The shell and its configuration)

[OUTPUT]
- shell_grants: The granted roots a shell of this run may use, none without an enforcing sandbox
- grant_command_paths: Those roots as the paths the command validator lets a command name
- get_or_create_bash_session: The healthy shell for a context, started when there is none
- close_bash_sessions: Close and forget every shell

[POS]
Shell lifecycle for ``LocalExecutor``; the executor keeps the registry, this module decides which shell serves a command.
"""

from __future__ import annotations

import hashlib
import logging
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.core.context_vars import standing_access_roots

if TYPE_CHECKING:
    from myrm_agent_harness.core.security.types import AccessRoot
    from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext
    from myrm_agent_harness.toolkits.code_execution.session import LocalPersistentSession

logger = logging.getLogger(__name__)

_GRANTS_MARK = "#grants:"


@cache
def sandbox_enforces() -> bool:
    """Whether commands run inside an OS sandbox; the platform and container do not change within a process."""
    from myrm_agent_harness.toolkits.code_execution.sandbox import detect_sandbox_provider

    return detect_sandbox_provider()[1].enabled


def shell_grants(work_dir: str) -> tuple[AccessRoot, ...]:
    """The granted roots a shell of this run may use: those the OS sandbox can enforce, none without a sandbox."""
    if not sandbox_enforces():
        return ()
    from myrm_agent_harness.toolkits.code_execution.sandbox.policy_bridge import sandbox_grant_roots

    return sandbox_grant_roots(work_dir, standing_access_roots())


def grant_command_paths(grants: tuple[AccessRoot, ...]) -> list[Path]:
    """The granted roots as paths a command may name."""
    return [Path(grant.path) for grant in grants]


def _grants_signature(grants: tuple[AccessRoot, ...]) -> str:
    shape = "|".join(sorted(f"{grant.path}:{int(grant.writable)}" for grant in grants))
    return hashlib.blake2s(shape.encode(), digest_size=4).hexdigest()


async def get_or_create_bash_session(
    sessions: dict[str, LocalPersistentSession],
    context: ExecutionContext,
    env: dict[str, str],
    *,
    workspace: Path | None,
    max_memory_mb: int,
) -> LocalPersistentSession:
    """Get the healthy persistent shell for this context or start one.

    A shell's sandbox is fixed when it starts, so a read-only run keeps its own shell and never reuses the
    writable run's under the same session id, and a change of the granted directories starts a new shell.
    """
    from myrm_agent_harness.toolkits.code_execution.session import (
        LocalPersistentSession,
        SessionConfig,
    )

    workspace_path = str(workspace) if workspace else "/tmp"
    grants = shell_grants(workspace_path)
    identity = f"{context.session_id or 'default'}{'_readonly' if context.readonly_workspace else ''}"
    session_key = f"{identity}{_GRANTS_MARK}{_grants_signature(grants)}" if grants else identity

    for stale_key in [key for key in sessions if key != session_key and key.partition(_GRANTS_MARK)[0] == identity]:
        logger.info(f" [LocalExecutor] Granted directories changed, closing Bash session: {stale_key}")
        await sessions.pop(stale_key).close()

    if session_key in sessions:
        session = sessions[session_key]
        if session.is_alive:
            if await session.check_health():
                logger.debug(f" [LocalExecutor] Reusing Bash session: {session_key}")
                return session
            logger.warning(f" [LocalExecutor] Unhealthy Bash session, restarting: {session_key}")
            await session.close()
            del sessions[session_key]

    logger.info(f" [LocalExecutor] Creating new Bash session: {session_key}")
    config = SessionConfig(
        session_id=session_key,
        work_dir=workspace_path,
        timeout=context.timeout or 300,
        env=env,
        max_memory_mb=max_memory_mb,
        readonly_workspace=context.readonly_workspace,
        allow_network=context.allow_network,
        granted_roots=grants,
    )
    session = LocalPersistentSession(config)
    await session.start()
    sessions[session_key] = session
    return session


async def close_bash_sessions(sessions: dict[str, LocalPersistentSession]) -> None:
    """Close every shell and forget it; one that fails to close does not keep the others open."""
    if not sessions:
        return
    logger.info(f" [LocalExecutor] Cleaning up {len(sessions)} Bash sessions")
    for session_key, session in list(sessions.items()):
        try:
            await session.close()
        except Exception as error:
            logger.warning(f" [LocalExecutor] Failed to close session {session_key}: {error}")
        finally:
            sessions.pop(session_key, None)
