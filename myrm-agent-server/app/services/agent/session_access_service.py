"""Server-side session directory access persistence and ContextVar bootstrap.

[INPUT]
- myrm_agent_harness.agent.security.session_access (POS: runtime session grant ContextVar)
- app.services.chat.chat_service::ChatService (POS: chat row persistence)

[OUTPUT]
- bootstrap_session_access_roots / persist_chat_session_access_roots
- grant_chat_session_access_root
- revoke_chat_session_access_root
- apply_directory_resume_grant
- is_directory_grant_allowed_for_deployment

[POS]
Server persistence and deployment-boundary gate for session-scoped directory grants.
"""

from __future__ import annotations

import logging
import os
from dataclasses import replace

from myrm_agent_harness.agent.security.session_access import (
    get_session_access_roots,
    grant_session_access_root,
    resolve_grant_directory_path,
    revoke_session_access_root,
    set_session_access_roots,
)
from myrm_agent_harness.agent.security.types import AccessRoot, PathPolicy, _default_path_policy

logger = logging.getLogger(__name__)


def access_roots_to_json(roots: tuple[AccessRoot, ...]) -> list[dict[str, object]]:
    return [
        {
            "path": root.path,
            "writable": root.writable,
            "label": root.label,
            "source": root.source,
        }
        for root in roots
    ]


def access_roots_from_json(raw: object) -> tuple[AccessRoot, ...]:
    if not isinstance(raw, list):
        return ()
    roots: list[AccessRoot] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path_obj = item.get("path")
        if not isinstance(path_obj, str) or not path_obj.strip():
            continue
        writable_obj = item.get("writable")
        label_obj = item.get("label")
        source_obj = item.get("source")
        roots.append(
            AccessRoot(
                path=path_obj.strip(),
                writable=bool(writable_obj) if isinstance(writable_obj, bool) else True,
                label=str(label_obj).strip() if isinstance(label_obj, str) else "",
                source=str(source_obj).strip() if isinstance(source_obj, str) else "persisted",
            )
        )
    return tuple(roots)


def bootstrap_session_access_roots(
    raw: object | None,
    *,
    workspace_dir: str | None = None,
    sandbox_active: bool = False,
) -> tuple[AccessRoot, ...]:
    roots = access_roots_from_json(raw)
    validated: list[AccessRoot] = []
    for root in roots:
        grant_path = resolve_grant_directory_path(root.path, workspace_dir)
        if not grant_path:
            continue
        if not is_directory_grant_allowed_for_deployment(
            grant_path,
            workspace_dir=workspace_dir,
            sandbox_active=sandbox_active,
        ):
            logger.warning(
                "Skipping persisted session access root outside deployment boundary: %s",
                grant_path,
            )
            continue
        validated.append(replace(root, path=grant_path))
    effective = tuple(validated)
    set_session_access_roots(effective)
    return effective


async def persist_chat_session_access_roots(
    chat_id: str,
    roots: tuple[AccessRoot, ...] | None = None,
) -> None:
    effective = roots if roots is not None else get_session_access_roots()
    from app.services.chat.chat_service import ChatService

    await ChatService.update_chat_fields(
        chat_id,
        {"session_access_roots": access_roots_to_json(effective)},
    )


async def grant_chat_session_access_root(
    chat_id: str,
    raw_path: str,
    *,
    writable: bool = True,
    label: str = "",
    source: str = "desktop_drag_drop",
    workspace_dir: str | None = None,
    sandbox_active: bool = False,
) -> tuple[AccessRoot, ...]:
    """Add one session access root and persist to chat record."""
    from app.services.chat.chat_service import ChatService

    chat = await ChatService.get_chat_metadata(chat_id)
    if chat is None:
        return ()

    persisted = access_roots_from_json(chat.session_access_roots)
    set_session_access_roots(persisted)

    policy = _default_path_policy()
    _apply_validated_grant(
        raw_path,
        writable=writable,
        source=source,
        workspace_dir=workspace_dir,
        sandbox_active=sandbox_active,
        policy=policy,
    )
    updated = get_session_access_roots()
    await persist_chat_session_access_roots(chat_id, updated)
    return updated


async def revoke_chat_session_access_root(
    chat_id: str,
    raw_path: str,
    *,
    workspace_dir: str | None = None,
) -> tuple[AccessRoot, ...]:
    """Remove one persisted session access root and sync the runtime ContextVar."""
    from app.services.chat.chat_service import ChatService

    chat = await ChatService.get_chat_metadata(chat_id)
    if chat is None:
        return ()

    persisted = access_roots_from_json(chat.session_access_roots)
    set_session_access_roots(persisted)

    updated = revoke_session_access_root(raw_path, workspace_root=workspace_dir)
    if updated == persisted:
        return persisted

    await persist_chat_session_access_roots(chat_id, updated)
    return updated


def _is_cloud_volume_deployment() -> bool:
    from myrm_agent_harness.runtime.execution_paths import PERSISTENT_ROOT

    return PERSISTENT_ROOT == "/persistent" and os.path.isdir("/persistent")


def _is_subpath(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent + os.sep)


def is_directory_grant_allowed_for_deployment(
    grant_path: str,
    *,
    workspace_dir: str | None,
    sandbox_active: bool,
) -> bool:
    """Gate directory grants by deployment mode (cloud volume vs local desktop)."""
    from myrm_agent_harness.agent.security.path_security import is_dangerous_path

    if sandbox_active:
        return False
    if is_dangerous_path(grant_path):
        return False
    if not _is_cloud_volume_deployment():
        return True

    from myrm_agent_harness.runtime.execution_paths import PERSISTENT_ROOT

    persistent_root = os.path.realpath(PERSISTENT_ROOT)
    normalized = os.path.realpath(grant_path)
    if _is_subpath(normalized, persistent_root):
        return True
    if workspace_dir:
        workspace_norm = os.path.realpath(os.path.expanduser(workspace_dir))
        if _is_subpath(normalized, workspace_norm):
            return True
    return False


def _apply_validated_grant(
    raw_path: str,
    *,
    writable: bool,
    source: str,
    workspace_dir: str | None,
    sandbox_active: bool,
    policy: PathPolicy | None = None,
) -> bool:
    grant_path = resolve_grant_directory_path(raw_path, workspace_dir)
    if not grant_path:
        return False
    if not is_directory_grant_allowed_for_deployment(
        grant_path,
        workspace_dir=workspace_dir,
        sandbox_active=sandbox_active,
    ):
        logger.warning(
            "Directory grant rejected by deployment boundary: path=%s workspace=%s",
            grant_path,
            workspace_dir,
        )
        return False

    roots_before = get_session_access_roots()
    effective_policy = policy or _default_path_policy()
    grant_session_access_root(
        AccessRoot(path=grant_path, writable=writable, source=source),
        policy=effective_policy,
        workspace_root=workspace_dir,
    )
    return len(get_session_access_roots()) > len(roots_before)


async def apply_directory_resume_grant(
    chat_id: str | None,
    resume_value: dict[str, object],
    *,
    sandbox_active: bool = False,
    workspace_dir: str | None = None,
) -> None:
    """Persist and bootstrap grants from request_directory or path-ASK resume payloads."""
    if sandbox_active:
        logger.warning("Directory grant ignored: sandbox mode active (chat_id=%s)", chat_id)
        return

    policy = _default_path_policy()
    granted = False

    if resume_value.get("granted") is True:
        path_obj = resume_value.get("path")
        writable_obj = resume_value.get("writable")
        if isinstance(path_obj, str) and path_obj.strip():
            granted = _apply_validated_grant(
                path_obj,
                writable=bool(writable_obj) if isinstance(writable_obj, bool) else False,
                source="hitl_grant",
                workspace_dir=workspace_dir,
                sandbox_active=sandbox_active,
                policy=policy,
            )
        if granted and chat_id:
            await persist_chat_session_access_roots(chat_id)
        return

    decisions = resume_value.get("decisions")
    if not isinstance(decisions, list):
        return

    for decision in decisions:
        if not isinstance(decision, dict) or decision.get("type") != "approve":
            continue
        extensions = decision.get("extensions")
        if not isinstance(extensions, dict):
            continue
        if extensions.get("grantDirectory") is not True:
            continue
        grant_meta = extensions.get("grantDirectoryMeta")
        if isinstance(grant_meta, dict):
            path_obj = grant_meta.get("path")
            writable_obj = grant_meta.get("writable")
            if isinstance(path_obj, str) and path_obj.strip():
                if _apply_validated_grant(
                    path_obj,
                    writable=bool(writable_obj) if isinstance(writable_obj, bool) else False,
                    source="path_ask_grant",
                    workspace_dir=workspace_dir,
                    sandbox_active=sandbox_active,
                    policy=policy,
                ):
                    granted = True

    if granted and chat_id:
        await persist_chat_session_access_roots(chat_id)
