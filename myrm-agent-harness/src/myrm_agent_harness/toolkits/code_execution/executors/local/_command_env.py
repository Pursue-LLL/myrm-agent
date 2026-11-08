"""Per-command environment of a bash command: skill settings that stay, credentials that do not.

[INPUT]
core.security.process_env::sanitize_env (POS: environment name/value filter), is_non_inheritable_env_var (POS: host-secret scrub)
core.security.safe_exec::credential_env_overrides (POS: credential issuer to environment variable mapping)
core.security.types::user_credentials_ctx (POS: request-scoped user credentials)
core.security.ephemeral_credentials::get_ephemeral_credential_store, command_digest, validate_credential_key (POS: one-time credentials approved for one command, and the names a command may be handed as a credential)
session.models::CommandEnv (POS: the environment applied around one command of a persistent shell)

[OUTPUT]
scrubbed_user_env: the part of a caller's environment that may reach a shell
skill_secret_env: the secret-named settings of the running skill, which only its own commands may read
collect_command_credentials: the credentials one command may read
build_command_env: the ``CommandEnv`` of one bash command

[POS]
A persistent shell outlives every command it runs, so a credential cannot be part of the shell: it belongs to the
command (which skill runs it, which approval granted it). This module decides what a command may read; the shell
driver applies it around that command and removes the credentials right after.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from myrm_agent_harness.toolkits.code_execution.session.models import CommandEnv

logger = logging.getLogger(__name__)


def scrubbed_user_env(user_env: Mapping[str, str] | None) -> dict[str, str]:
    """Return ``user_env`` without the names a shell must never receive (secrets, loaders, proxies)."""
    if not user_env:
        return {}
    from myrm_agent_harness.core.security.process_env import is_non_inheritable_env_var, sanitize_env

    return {name: value for name, value in sanitize_env(dict(user_env)).items() if not is_non_inheritable_env_var(name)}


def skill_secret_env(skill_env: Mapping[str, str] | None) -> dict[str, str]:
    """Return the settings of the running skill that a shell never takes as environment: its own secrets.

    A person typed them into this skill's settings, so they are the skill's to read, around its own commands only.
    The names are held to the rule of a one-time credential: one that makes a program run what its value names
    (``LD_PRELOAD``, ``NODE_OPTIONS``) or that shapes the shell itself (``PATH``, ``IFS``) is not delivered.
    Settings the shell does take stay out of this set, so their values are not masked in the command's output.
    """
    if not skill_env:
        return {}
    from myrm_agent_harness.core.security.ephemeral_credentials import validate_credential_key
    from myrm_agent_harness.core.security.process_env import is_non_inheritable_env_var

    secrets: dict[str, str] = {}
    for name, value in skill_env.items():
        if not is_non_inheritable_env_var(name):
            continue
        try:
            validate_credential_key(name)
        except ValueError as error:
            logger.warning("[LOCAL_EXECUTOR] Skill setting '%s' is not delivered: %s", name, error)
            continue
        secrets[name] = value
    return secrets


def collect_command_credentials(allowed_issuers: list[str] | None, command: str | None) -> dict[str, str]:
    """Return the credentials ``command`` may read.

    ``allowed_issuers``: ``None`` injects every user credential, ``[]`` none, otherwise only the listed issuers.
    ``command`` is the text the agent issued and a person approved, not the script prepared from it. One-time
    credentials are consumed here, each only for the command digest it was approved for.
    """
    from myrm_agent_harness.core.security.safe_exec import credential_env_overrides
    from myrm_agent_harness.core.security.types import user_credentials_ctx

    credentials: dict[str, str] = {}
    user_credentials = user_credentials_ctx.get()
    if user_credentials:
        credentials.update(credential_env_overrides(user_credentials, allowed_issuers=allowed_issuers))

    credentials.update(_consume_ephemeral_credentials(command))
    return credentials


def _consume_ephemeral_credentials(command: str | None) -> dict[str, str]:
    """Consume the one-time credentials staged for this approval session that are valid for ``command``."""
    consumed: dict[str, str] = {}
    try:
        from myrm_agent_harness.core.context_vars import approval_session_var
        from myrm_agent_harness.core.security.ephemeral_credentials import (
            command_digest,
            get_ephemeral_credential_store,
            validate_credential_key,
        )

        current_session = approval_session_var.get()
        if not current_session:
            return consumed
        store = get_ephemeral_credential_store()
        action_digest = command_digest(command) if command and command.strip() else None
        for summary in store.list_summaries(current_session):
            if summary.is_consumed or summary.is_expired:
                continue
            try:
                value = store.consume_credential(current_session, summary.handle_id, action_digest=action_digest)
                name = validate_credential_key(summary.key)
            except ValueError as error:
                logger.warning(
                    "[LOCAL_EXECUTOR] Ephemeral credential handle '%s' skipped: %s", summary.handle_id, error
                )
                continue
            consumed[f"MYRM_CREDENTIAL_{name}"] = value
            consumed[name] = value
    except Exception as error:
        logger.debug("[LOCAL_EXECUTOR] Ephemeral credential injection skipped: %s", error)
    return consumed


def build_command_env(
    user_env: Mapping[str, str] | None,
    allowed_issuers: list[str] | None,
    command: str | None,
    skill_env: Mapping[str, str] | None = None,
) -> CommandEnv:
    """Return the environment one bash command runs with on top of its shell's own.

    A credential approved or issued for the command wins over a skill setting of the same name.
    """
    return CommandEnv(
        sticky=scrubbed_user_env(user_env),
        scoped={**skill_secret_env(skill_env), **collect_command_credentials(allowed_issuers, command)},
    )
