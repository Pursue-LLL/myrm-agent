"""[INPUT]
- .common (POS: shared constants and preset state)

[OUTPUT]
- _provider_is_ready, _wiki_has_content, _agent_has_required_tools, _build_checklist, _resolve_agent

[POS]
Second Brain preset: readiness checks (provider / wiki / agent tools) and the checklist.
"""

from __future__ import annotations

from copy import deepcopy

from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.config_readiness import ProviderConfigChecker
from app.database.dto import AgentCreate, AgentUpdate
from app.services.agent.agent_service import AgentService
from app.services.agent.template_utils import ensure_skills_enabled, resolve_i18n
from app.services.onboarding.schemas import (
    ChecklistItem,
    SecondBrainPresetState,
)
from app.services.wiki.vault import vault_has_wiki_content

from . import common
from .common import (
    _REQUIRED_TOOLS,
    _TEMPLATE_ID,
    _USER_ID,
    logger,
)


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


async def _build_checklist(
    *,
    agent_id: str | None,
    cron_job_id: str | None,
    delta_cron_job_id: str | None,
    maintain_cron_job_id: str | None,
) -> list[ChecklistItem]:
    agent_ready = False
    if agent_id:
        profile = await AgentService.get_agent_by_id(agent_id)
        if profile is not None:
            agent_ready = _agent_has_required_tools(profile.tools_allowed)

    cron_ready = False
    if cron_job_id and delta_cron_job_id and maintain_cron_job_id:
        mgr = common.get_cron_manager()
        read_later_job = await mgr.get_job(cron_job_id, _USER_ID)
        delta_job = await mgr.get_job(delta_cron_job_id, _USER_ID)
        maintain_job = await mgr.get_job(maintain_cron_job_id, _USER_ID)
        cron_ready = read_later_job is not None and delta_job is not None and maintain_job is not None

    vault_ready = _wiki_has_content(agent_id)
    provider_ready = await _provider_is_ready()
    from app.services.wiki.dedup_runner import wiki_dedup_checklist_ready

    corpus_dedup_ready = wiki_dedup_checklist_ready(agent_id=agent_id)

    return [
        ChecklistItem(id="agent_tools", ready=agent_ready),
        ChecklistItem(id="cron_job", ready=cron_ready),
        ChecklistItem(id="vault_content", ready=vault_ready),
        ChecklistItem(id="corpus_dedup", ready=corpus_dedup_ready),
        ChecklistItem(id="provider_ready", ready=provider_ready),
    ]


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

    template_data = common._load_template_data()
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
