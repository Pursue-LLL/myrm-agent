"""Second Brain onboarding preset — agent template + dual cron jobs + checklist.

[INPUT]
- assets/prebuilt_agents/second_brain_assistant.yaml (POS: agent template seed)
- app.services.agent.template_utils::ensure_skills_enabled (POS: prebuilt skill enablement)
- app.core.cron.blueprints::fill_blueprint (POS: read_it_later + wiki_morning_delta blueprints)
- app.services.config.service::config_service (POS: preset state persistence)
- app.services.wiki.vault_resolver::seed_agent_vault_from_default (POS: default→agent vault seed)

[OUTPUT]
- apply_second_brain_preset(): create/reuse agent + read-it-later + wiki-morning-delta crons, persist checklist state
- get_second_brain_preset_status(): honest 4-item readiness checklist; clears stale preset when stored agent was deleted
- _apply_success_message(): localized apply toast copy
- _clear_preset_state(): delete persisted secondBrainPreset config

[POS]
Business-layer onboarding orchestration for Obsidian / LLM-Wiki migration users.
Reuses template + cron primitives; no new harness meta-tools.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime

import yaml
from myrm_agent_harness.toolkits.cron.types import CronJobPatch, JobType, Schedule, ScheduleKind, SessionTarget

from app.services.agent.template_utils import PREBUILT_AGENTS_DIR, ensure_skills_enabled, resolve_i18n
from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.config_readiness import ProviderConfigChecker
from app.core.cron.adapters.setup import get_cron_manager
from app.core.cron.blueprints import fill_blueprint
from app.database.dto import AgentCreate, AgentUpdate
from app.services.agent.agent_service import AgentService
from app.services.config.service import config_service
from app.services.onboarding.schemas import (
    ChecklistItem,
    SecondBrainApplyResponse,
    SecondBrainPresetState,
    SecondBrainStatusResponse,
)
from app.services.wiki.vault_resolver import seed_agent_vault_from_default, vault_has_wiki_content

logger = logging.getLogger(__name__)

_CONFIG_KEY = "secondBrainPreset"
_TEMPLATE_ID = "second_brain_assistant"
_CRON_JOB_NAME = "Second Brain · Read-it-Later"
_CRON_DELTA_JOB_NAME = "Second Brain · Wiki Morning Delta"
_USER_ID = "default"
_DEVICE_ID = "second-brain-preset"
_REQUIRED_TOOLS = frozenset({"memory", "wiki", "cron"})


class SecondBrainPresetError(Exception):
    """Preset apply failed with a user-visible message."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(slots=True)
class _ApplyMutation:
    created_agent_id: str | None = None
    created_cron_job_ids: tuple[str, ...] = ()


def _load_template_data() -> dict[str, object]:
    file_path = os.path.join(PREBUILT_AGENTS_DIR, f"{_TEMPLATE_ID}.yaml")
    if not os.path.isfile(file_path):
        msg = f"Second Brain template missing: {_TEMPLATE_ID}"
        raise FileNotFoundError(msg)
    with open(file_path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or not data:
        msg = "Second Brain template is empty"
        raise ValueError(msg)
    return data


def _normalize_locale(accept_language: str | None) -> str:
    if accept_language and "zh" in accept_language.lower():
        return "zh"
    return "en"


async def _load_preset_state() -> SecondBrainPresetState | None:
    record = await config_service.get(_CONFIG_KEY)
    if record is None:
        return None
    try:
        return SecondBrainPresetState.model_validate(record.value)
    except Exception:
        logger.warning("Invalid secondBrainPreset config; treating as unset")
        return None


async def _save_preset_state(state: SecondBrainPresetState) -> None:
    await config_service.set(
        config_key=_CONFIG_KEY,
        value=state.model_dump(mode="json"),
        device_id=_DEVICE_ID,
    )


async def _clear_preset_state() -> None:
    await config_service.delete(_CONFIG_KEY)


async def reconcile_second_brain_cron_ids(id_remaps: dict[str, str]) -> None:
    """Update stored preset cron ids after read-it-later hygiene recreates jobs."""
    if not id_remaps:
        return
    state = await _load_preset_state()
    if state is None:
        return
    cron_job_id = id_remaps.get(state.cron_job_id, state.cron_job_id) if state.cron_job_id else None
    delta_cron_job_id = (
        id_remaps.get(state.delta_cron_job_id, state.delta_cron_job_id) if state.delta_cron_job_id else None
    )
    if cron_job_id == state.cron_job_id and delta_cron_job_id == state.delta_cron_job_id:
        return
    await _save_preset_state(
        state.model_copy(
            update={
                "cron_job_id": cron_job_id,
                "delta_cron_job_id": delta_cron_job_id,
            }
        )
    )


async def _run_read_it_later_hygiene() -> None:
    from app.services.wiki.source_sync.read_it_later_hygiene import migrate_stale_read_it_later_jobs

    result = await migrate_stale_read_it_later_jobs()
    if result.migrated_count:
        logger.info("Read-it-later cron hygiene migrated %d job(s)", result.migrated_count)
    await reconcile_second_brain_cron_ids(result.id_remaps)


async def _maybe_enable_wiki_gmail_source() -> None:
    from app.services.wiki.source_sync.defaults import maybe_enable_wiki_gmail_on_google_connect

    await maybe_enable_wiki_gmail_on_google_connect(respect_existing_config=False)


def _apply_success_message(*, locale: str, vault_files_seeded: int) -> str:
    if vault_files_seeded > 0:
        if locale == "en":
            return f"Second Brain preset applied; synced {vault_files_seeded} wiki files"
        return f"第二大脑预设已应用，已同步 {vault_files_seeded} 个 wiki 文件"
    if locale == "en":
        return "Second Brain preset applied successfully"
    return "第二大脑预设已应用"


async def _provider_is_ready() -> bool:
    try:
        user_configs = await load_user_configs()
    except Exception as exc:
        logger.warning("Provider readiness check failed: %s", exc)
        return False
    checker = ProviderConfigChecker()
    result = checker.check(user_configs.providers_dict)
    return bool(result.is_ready)


def _wiki_has_content(agent_id: str | None = None) -> bool:
    return vault_has_wiki_content(agent_id)


def _agent_has_required_tools(tools: list[str] | tuple[str, ...] | None) -> bool:
    if not tools:
        return False
    enabled = set(tools)
    return _REQUIRED_TOOLS.issubset(enabled)


async def _resolve_agent(
    *,
    locale: str,
    existing_state: SecondBrainPresetState | None,
) -> tuple[str, str, bool]:
    """Return (agent_id, agent_name, created). Reuses stored or name-matched agents."""
    if existing_state and existing_state.agent_id:
        profile = await AgentService.get_agent_by_id(existing_state.agent_id)
        if profile is not None and not profile.built_in:
            if _agent_has_required_tools(profile.tools_allowed):
                name = profile.display_name or existing_state.agent_name or "Second Brain"
                return profile.id, name, False
            await AgentService.update_agent(
                profile.id,
                AgentUpdate(enabled_builtin_tools=list(_REQUIRED_TOOLS | {"web_search", "structured_clarify"})),
            )
            updated = await AgentService.get_agent_by_id(profile.id)
            name = (updated.display_name if updated else profile.display_name) or "Second Brain"
            return profile.id, name, False

    template_data = _load_template_data()
    for name_key in ("en", "zh"):
        name_obj = template_data.get("name")
        if isinstance(name_obj, dict):
            candidate = str(name_obj.get(name_key, "")).strip()
        else:
            candidate = str(name_obj or "").strip()
        if candidate:
            matches = await AgentService.get_agents_by_name(candidate)
            for match in matches:
                if match.built_in:
                    continue
                if _agent_has_required_tools(match.tools_allowed):
                    return match.id, match.display_name or candidate, False

    data = deepcopy(template_data)
    prebuilt_skill_ids_raw = data.pop("prebuilt_skill_ids", [])
    prebuilt_skill_ids = [str(s) for s in prebuilt_skill_ids_raw] if isinstance(prebuilt_skill_ids_raw, list) else []
    await ensure_skills_enabled(prebuilt_skill_ids, _TEMPLATE_ID)

    if data.get("name"):
        data["name"] = resolve_i18n(data["name"], locale)
    else:
        data["name"] = _TEMPLATE_ID

    if data.get("description"):
        data["description"] = resolve_i18n(data["description"], locale)

    data["is_built_in"] = False
    if "skill_ids" not in data or data["skill_ids"] is None:
        data["skill_ids"] = []
    skill_ids: list[str] = list(data["skill_ids"])
    for skill_id in prebuilt_skill_ids:
        if skill_id not in skill_ids:
            skill_ids.append(skill_id)
    data["skill_ids"] = skill_ids
    data.pop("members", None)
    data.pop("use_cases", None)

    agent_data = AgentCreate.model_validate(data)
    created = await AgentService.create_agent(agent_data)
    return created.id, created.display_name or str(data["name"]), True


async def _find_preset_cron_job(*, job_name: str, stored_job_id: str | None) -> str | None:
    mgr = get_cron_manager()
    jobs = await mgr.list_jobs(_USER_ID)
    for job in jobs:
        if job.name == job_name or job.name.startswith(f"{job_name} ("):
            return job.id
    if stored_job_id:
        existing = await mgr.get_job(stored_job_id, _USER_ID)
        if existing is not None:
            return existing.id
    return None


async def _find_read_it_later_cron_job() -> str | None:
    state = await _load_preset_state()
    stored_id = state.cron_job_id if state else None
    return await _find_preset_cron_job(job_name=_CRON_JOB_NAME, stored_job_id=stored_id)


async def _find_wiki_morning_delta_cron_job() -> str | None:
    state = await _load_preset_state()
    stored_id = state.delta_cron_job_id if state else None
    return await _find_preset_cron_job(job_name=_CRON_DELTA_JOB_NAME, stored_job_id=stored_id)


async def _ensure_blueprint_cron(
    *,
    blueprint_id: str,
    job_name: str,
    slot_values: dict[str, str],
    agent_id: str,
    locale: str,
    find_existing_job_id: Callable[[], Awaitable[str | None]],
) -> tuple[str | None, bool]:
    mgr = get_cron_manager()
    fill = fill_blueprint(blueprint_id, slot_values, locale=locale)
    if fill is None:
        raise SecondBrainPresetError(f"{blueprint_id} cron blueprint is unavailable")

    existing_id = await find_existing_job_id()
    if existing_id:
        job = await mgr.get_job(existing_id, _USER_ID)
        if job is not None:
            needs_rebuild = fill.command is not None and (
                job.command != fill.command or job.job_type != JobType(fill.job_type)
            )
            if needs_rebuild:
                await mgr.delete_job(existing_id, _USER_ID)
                existing_id = None
            elif job.agent_id != agent_id:
                await mgr.update_job(existing_id, _USER_ID, CronJobPatch(agent_id=agent_id))
                return existing_id, False
            else:
                return existing_id, False

    schedule = Schedule(
        kind=ScheduleKind.CRON,
        expr=fill.schedule.expr,
        tz=fill.schedule.tz,
    )
    job = await mgr.create_job(
        _USER_ID,
        job_name,
        JobType(fill.job_type),
        schedule,
        prompt=fill.prompt,
        agent_id=agent_id,
        required_capabilities=fill.required_capabilities,
        tools_allowed=fill.tools_allowed,
        session_target=SessionTarget(fill.session_target),
        deduplicate=fill.deduplicate,
        skip_if_active=fill.skip_if_active,
        timeout_seconds=fill.timeout_seconds or 300,
        pre_condition_script=fill.pre_condition_script,
        command=fill.command,
    )
    return job.id, True


async def _ensure_read_it_later_cron(*, agent_id: str, locale: str) -> tuple[str | None, bool]:
    return await _ensure_blueprint_cron(
        blueprint_id="read_it_later",
        job_name=_CRON_JOB_NAME,
        slot_values={"time": "06:00", "weekdays": "everyday"},
        agent_id=agent_id,
        locale=locale,
        find_existing_job_id=_find_read_it_later_cron_job,
    )


async def _ensure_wiki_morning_delta_cron(*, agent_id: str, locale: str) -> tuple[str | None, bool]:
    return await _ensure_blueprint_cron(
        blueprint_id="wiki_morning_delta",
        job_name=_CRON_DELTA_JOB_NAME,
        slot_values={"time": "07:00", "weekdays": "everyday"},
        agent_id=agent_id,
        locale=locale,
        find_existing_job_id=_find_wiki_morning_delta_cron_job,
    )


async def _rollback_apply(mutation: _ApplyMutation) -> None:
    if mutation.created_cron_job_ids:
        mgr = get_cron_manager()
        for cron_job_id in mutation.created_cron_job_ids:
            try:
                await mgr.delete_job(cron_job_id, _USER_ID)
            except Exception as exc:
                logger.warning("Rollback failed to delete cron job %s: %s", cron_job_id, exc)
    if mutation.created_agent_id:
        try:
            await AgentService.delete_agent(mutation.created_agent_id)
        except Exception as exc:
            logger.warning("Rollback failed to delete agent %s: %s", mutation.created_agent_id, exc)


async def _build_checklist(
    *,
    agent_id: str | None,
    cron_job_id: str | None,
    delta_cron_job_id: str | None,
) -> list[ChecklistItem]:
    agent_ready = False
    if agent_id:
        profile = await AgentService.get_agent_by_id(agent_id)
        if profile is not None:
            agent_ready = _agent_has_required_tools(profile.tools_allowed)

    cron_ready = False
    if cron_job_id and delta_cron_job_id:
        mgr = get_cron_manager()
        read_later_job = await mgr.get_job(cron_job_id, _USER_ID)
        delta_job = await mgr.get_job(delta_cron_job_id, _USER_ID)
        cron_ready = read_later_job is not None and delta_job is not None

    vault_ready = _wiki_has_content(agent_id)
    provider_ready = await _provider_is_ready()

    return [
        ChecklistItem(id="agent_tools", ready=agent_ready),
        ChecklistItem(id="cron_job", ready=cron_ready),
        ChecklistItem(id="vault_content", ready=vault_ready),
        ChecklistItem(id="provider_ready", ready=provider_ready),
    ]


async def get_second_brain_preset_status(*, accept_language: str | None = None) -> SecondBrainStatusResponse:
    _ = accept_language
    await _run_read_it_later_hygiene()
    state = await _load_preset_state()
    if state is None or not state.agent_id:
        checklist = await _build_checklist(agent_id=None, cron_job_id=None, delta_cron_job_id=None)
        return SecondBrainStatusResponse(applied=False, checklist=checklist)

    profile = await AgentService.get_agent_by_id(state.agent_id)
    if profile is None:
        logger.info(
            "Second Brain preset stored agent %s no longer exists; clearing preset config",
            state.agent_id,
        )
        await _clear_preset_state()
        checklist = await _build_checklist(agent_id=None, cron_job_id=None, delta_cron_job_id=None)
        return SecondBrainStatusResponse(applied=False, checklist=checklist)

    checklist = await _build_checklist(
        agent_id=state.agent_id,
        cron_job_id=state.cron_job_id,
        delta_cron_job_id=state.delta_cron_job_id,
    )
    return SecondBrainStatusResponse(
        applied=True,
        agent_id=state.agent_id,
        agent_name=state.agent_name,
        cron_job_id=state.cron_job_id,
        delta_cron_job_id=state.delta_cron_job_id,
        applied_at=state.applied_at,
        checklist=checklist,
    )


async def apply_second_brain_preset(*, accept_language: str | None = None) -> SecondBrainApplyResponse:
    locale = _normalize_locale(accept_language)
    previous_state = await _load_preset_state()
    previous_snapshot = deepcopy(previous_state.model_dump(mode="json")) if previous_state else None
    mutation = _ApplyMutation()

    try:
        agent_id, agent_name, agent_created = await _resolve_agent(
            locale=locale,
            existing_state=previous_state,
        )
        if agent_created:
            mutation.created_agent_id = agent_id

        seed_result = seed_agent_vault_from_default(agent_id)
        if seed_result.files_copied:
            logger.info(
                "Second Brain preset seeded %d wiki files into agent %s",
                seed_result.files_copied,
                agent_id,
            )

        cron_job_id, cron_created = await _ensure_read_it_later_cron(agent_id=agent_id, locale=locale)
        if cron_created and cron_job_id:
            mutation.created_cron_job_ids = (*mutation.created_cron_job_ids, cron_job_id)

        delta_cron_job_id, delta_cron_created = await _ensure_wiki_morning_delta_cron(
            agent_id=agent_id,
            locale=locale,
        )
        if delta_cron_created and delta_cron_job_id:
            mutation.created_cron_job_ids = (*mutation.created_cron_job_ids, delta_cron_job_id)

        await _maybe_enable_wiki_gmail_source()

        applied_at = datetime.now(UTC).isoformat()
        await _save_preset_state(
            SecondBrainPresetState(
                agent_id=agent_id,
                agent_name=agent_name,
                cron_job_id=cron_job_id,
                delta_cron_job_id=delta_cron_job_id,
                applied_at=applied_at,
            )
        )

        checklist = await _build_checklist(
            agent_id=agent_id,
            cron_job_id=cron_job_id,
            delta_cron_job_id=delta_cron_job_id,
        )
        message = _apply_success_message(
            locale=locale,
            vault_files_seeded=seed_result.files_copied,
        )
        return SecondBrainApplyResponse(
            success=True,
            message=message,
            agent_id=agent_id,
            agent_name=agent_name,
            cron_job_id=cron_job_id,
            delta_cron_job_id=delta_cron_job_id,
            checklist=checklist,
            applied_at=applied_at,
        )
    except Exception:
        await _rollback_apply(mutation)
        if previous_snapshot is not None:
            try:
                await config_service.set(
                    config_key=_CONFIG_KEY,
                    value=previous_snapshot,
                    device_id=f"{_DEVICE_ID}-rollback",
                )
            except Exception as exc:
                logger.warning("Failed to restore secondBrainPreset snapshot: %s", exc)
        raise
