"""Resolve or create the agent a Telegram onboarding binds to, serialised across tasks and processes.

[INPUT]
- app.services.agent.agent_service::AgentService (POS: 业务层Agent服务)
- app.database.dto::AgentCreate (POS: Pydantic数据模型)
- app.config.settings::settings (POS: 应用配置；状态目录决定跨进程锁文件的位置)

[OUTPUT]
- resolve_or_create_telegram_agent: the bound agent's id and display name, plus the id of the agent this call created
  (the one a failed onboarding must delete)

[POS]
Agent step of the Telegram onboarding wizard. Reuses a channel-bindable agent of the requested name (a search-mode
agent never is one) or creates it, under an in-process lock and a per-name file lock in the state directory, so
concurrent onboardings neither create duplicates nor interleave; a run that finds the file lock held gets
``409 TELEGRAM_ONBOARDING_IN_PROGRESS``.
"""

import asyncio
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException
from filelock import FileLock, Timeout

if TYPE_CHECKING:
    from myrm_agent_harness.backends.profiles.types import AgentProfile

_TELEGRAM_AGENT_RESOLUTION_LOCK = asyncio.Lock()
_TELEGRAM_AGENT_CROSS_PROCESS_LOCK_TIMEOUT_SEC = 0.0
_TELEGRAM_ONBOARDING_IN_PROGRESS_CODE = "TELEGRAM_ONBOARDING_IN_PROGRESS"
_TELEGRAM_ONBOARDING_IN_PROGRESS_MESSAGE = "Telegram onboarding is already in progress. Please retry shortly."


def _normalize_telegram_agent_name(raw: str) -> str:
    return raw.strip().casefold()


def _telegram_agent_cross_process_lock_path(assistant_name: str) -> Path:
    from app.config.settings import settings

    normalized_name = _normalize_telegram_agent_name(assistant_name)
    lock_hash = hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()
    lock_dir = Path(settings.database.state_dir) / "locks" / "onboarding"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / f"telegram-agent-{lock_hash}.lock"


def _acquire_telegram_agent_cross_process_lock(lock: FileLock) -> None:
    try:
        lock.acquire(timeout=_TELEGRAM_AGENT_CROSS_PROCESS_LOCK_TIMEOUT_SEC)
    except Timeout as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": _TELEGRAM_ONBOARDING_IN_PROGRESS_CODE,
                "message": _TELEGRAM_ONBOARDING_IN_PROGRESS_MESSAGE,
            },
        ) from exc


def _release_telegram_agent_cross_process_lock(lock: FileLock) -> None:
    if lock.is_locked:
        lock.release()


def _is_channel_bindable_agent(agent_profile: object) -> bool:
    metadata = getattr(agent_profile, "metadata", None)
    if not isinstance(metadata, dict):
        return True
    prompt_mode = metadata.get("prompt_mode")
    return not (isinstance(prompt_mode, str) and prompt_mode.lower() == "search")


def _pick_first_channel_bindable_agent(candidates: list["AgentProfile"]) -> "AgentProfile | None":
    for candidate in candidates:
        if _is_channel_bindable_agent(candidate):
            return candidate
    return None


async def resolve_or_create_telegram_agent(
    *,
    name: str,
    description: str | None,
    system_prompt: str | None,
) -> tuple[str, str, str | None]:
    """Return ``(agent_id, display_name, created_agent_id)``; ``created_agent_id`` is set only when this call created the agent."""
    from app.database.dto import AgentCreate
    from app.services.agent.agent_service import AgentService

    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(status_code=422, detail="Assistant name is required")
    normalized_description = (description or "").strip()
    normalized_system_prompt = (system_prompt or "").strip()

    async with _TELEGRAM_AGENT_RESOLUTION_LOCK:
        cross_process_lock = FileLock(str(_telegram_agent_cross_process_lock_path(normalized_name)))
        _acquire_telegram_agent_cross_process_lock(cross_process_lock)
        try:
            name_matches = await AgentService.get_agents_by_name(normalized_name)
            existing_bindable = _pick_first_channel_bindable_agent(name_matches)
            if existing_bindable is not None:
                existing_id = str(existing_bindable.id)
                existing_name = str(getattr(existing_bindable, "display_name", "") or normalized_name)
                return existing_id, existing_name, None

            create_name = normalized_name
            if name_matches:
                create_name = f"{normalized_name} (General)"
                general_name_matches = await AgentService.get_agents_by_name(create_name)
                existing_general = _pick_first_channel_bindable_agent(general_name_matches)
                if existing_general is not None:
                    existing_id = str(existing_general.id)
                    existing_name = str(getattr(existing_general, "display_name", "") or create_name)
                    return existing_id, existing_name, None

            default_description = "Personal Telegram assistant created by onboarding wizard."
            default_system_prompt = (
                "You are a practical personal assistant running on Telegram. Keep replies concise, actionable, and privacy-aware."
            )

            created = await AgentService.create_agent(
                AgentCreate(
                    name=create_name,
                    description=normalized_description or default_description,
                    system_prompt=normalized_system_prompt or default_system_prompt,
                    prompt_mode="full",
                    agent_type="individual",
                )
            )
            return created.id, created.display_name or create_name, created.id
        finally:
            _release_telegram_agent_cross_process_lock(cross_process_lock)
