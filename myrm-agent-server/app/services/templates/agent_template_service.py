"""[INPUT]
- assets/prebuilt_agents/*.yaml (POS: Prebuilt agent template seed files)
- app.services.agent.template_utils::resolve_i18n (POS: Multi-language resolution)
- app.services.agent.template_utils::ensure_skills_enabled (POS: Skill enablement check)
- app.services.agent.agent_service::AgentService (POS: Agent CRUD service)

[OUTPUT]
- AgentTemplateService: Unified service for discovering, detailing, and instantiating templates
- TemplateDetail: Enriched template model with sandbox wiki structure blueprint
- TemplateCategory: Valid category definitions for marketplace filtering

[POS]
app.services.templates module facade and business service.
Provides structured marketplace data and zero-prompt one-click cloning.
"""

from __future__ import annotations

import glob
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

from app.database.dto import AgentCreate
from app.services.agent.agent_service import AgentService
from app.services.agent.template_utils import (
    PREBUILT_AGENTS_DIR,
    ensure_skills_enabled,
    resolve_i18n,
)
from app.services.features.product_surface import is_hidden_prebuilt_template

logger = logging.getLogger(__name__)


# Standard wiki directory blueprint recommended for each industry category
CATEGORY_WIKI_BLUEPRINTS: dict[str, list[str]] = {
    "engineering": ["architecture/", "benchmarks/", "refactor_plans/", "runbooks/"],
    "office": ["templates/", "meeting_minutes/", "policies/", "archive/"],
    "commerce": ["product_catalog/", "competitor_intel/", "order_flows/"],
    "team": ["shared_knowledge/", "coordination_rules/", "member_profiles/"],
    "general": ["notes/", "checklists/", "resources/"],
}


@dataclass(slots=True)
class TemplateMemberInfo:
    role: str
    name: str
    description: str | None = None


@dataclass(slots=True)
class TemplatePreviewMeta:
    id: str
    name: str
    description: str | None
    avatar_url: str | None
    agent_type: str
    category: str
    is_pareto_preset: bool
    cost_reduction_ratio: float | None
    use_cases: list[str] = field(default_factory=list)
    builtin_tools_count: int = 0
    skills_count: int = 0
    members: list[TemplateMemberInfo] = field(default_factory=list)
    wiki_blueprint: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CloneTemplateOptions:
    template_id: str
    custom_name: str | None = None
    accept_language: str = "en"
    init_wiki_blueprint: bool = True


class AgentTemplateService:
    """Enterprise-grade service for querying prebuilt agent templates and zero-prompt cloning."""

    @classmethod
    def list_templates(cls, accept_language: str = "en") -> list[TemplatePreviewMeta]:
        """Discover and return all visible prebuilt agent templates sorted by category."""
        if not os.path.isdir(PREBUILT_AGENTS_DIR):
            logger.warning("Prebuilt agents directory missing: %s", PREBUILT_AGENTS_DIR)
            return []

        yaml_files = sorted(glob.glob(os.path.join(PREBUILT_AGENTS_DIR, "*.yaml")))
        results: list[TemplatePreviewMeta] = []

        for file_path in yaml_files:
            template_id = os.path.basename(file_path).replace(".yaml", "")
            if is_hidden_prebuilt_template(template_id):
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_data = yaml.safe_load(f)
                if not raw_data:
                    continue

                meta = cls._parse_raw_template(template_id, raw_data, accept_language)
                results.append(meta)
            except Exception as e:
                logger.error("Failed to load template %s: %s", template_id, e)

        return results

    @classmethod
    def get_template(cls, template_id: str, accept_language: str = "en") -> TemplatePreviewMeta | None:
        """Fetch a single template by ID."""
        file_path = os.path.join(PREBUILT_AGENTS_DIR, f"{template_id}.yaml")
        if not os.path.isfile(file_path) or is_hidden_prebuilt_template(template_id):
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)
            if not raw_data:
                return None
            return cls._parse_raw_template(template_id, raw_data, accept_language)
        except Exception as e:
            logger.error("Failed to read template %s: %s", template_id, e)
            return None

    @classmethod
    async def clone_and_instantiate(
        cls,
        options: CloneTemplateOptions,
    ) -> dict[str, Any]:
        """Instantiate a template into a live agent with zero-prompt setup and optional name override."""
        file_path = os.path.join(PREBUILT_AGENTS_DIR, f"{options.template_id}.yaml")
        if not os.path.isfile(file_path):
            raise ValueError(f"Template {options.template_id} not found")

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data:
            raise ValueError(f"Template {options.template_id} is empty")

        agent_type = data.get("agent_type", "individual")

        if agent_type == "team":
            return await cls._instantiate_team_internal(data, options)
        return await cls._instantiate_individual_internal(data, options)

    @classmethod
    def _parse_raw_template(
        cls,
        template_id: str,
        data: dict[str, Any],
        accept_lang: str,
    ) -> TemplatePreviewMeta:
        name = resolve_i18n(data.get("name"), accept_lang) or template_id
        description = resolve_i18n(data.get("description"), accept_lang) if data.get("description") else None
        agent_type = data.get("agent_type", "individual")

        category = cls._infer_category(template_id, data.get("category"), agent_type)
        wiki_blueprint = CATEGORY_WIKI_BLUEPRINTS.get(category, CATEGORY_WIKI_BLUEPRINTS["general"])

        use_cases: list[str] = []
        if agent_type == "team":
            use_cases = [resolve_i18n(uc, accept_lang) for uc in data.get("use_cases", [])]
        else:
            use_cases = [resolve_i18n(sp, accept_lang) for sp in data.get("suggestion_prompts", [])]

        members: list[TemplateMemberInfo] = []
        if agent_type == "team":
            for m in data.get("members", []):
                members.append(
                    TemplateMemberInfo(
                        role=m.get("role", "member"),
                        name=resolve_i18n(m.get("name"), accept_lang),
                        description=resolve_i18n(m.get("description"), accept_lang) if m.get("description") else None,
                    )
                )

        tools = list(data.get("enabled_builtin_tools") or [])
        skills = list(data.get("skill_ids") or []) + list(data.get("prebuilt_skill_ids") or [])

        return TemplatePreviewMeta(
            id=template_id,
            name=name,
            description=description,
            avatar_url=data.get("avatar_url"),
            agent_type=agent_type,
            category=category,
            is_pareto_preset=bool(data.get("is_pareto_preset", False)),
            cost_reduction_ratio=(
                float(data["cost_reduction_ratio"]) if data.get("cost_reduction_ratio") is not None else None
            ),
            use_cases=use_cases,
            builtin_tools_count=len(tools),
            skills_count=len(set(skills)),
            members=members,
            wiki_blueprint=wiki_blueprint,
        )

    @classmethod
    def _infer_category(cls, template_id: str, raw_category: str | None, agent_type: str) -> str:
        if raw_category:
            return raw_category
        if agent_type == "team":
            return "team"
        if template_id in (
            "frontend_development_expert",
            "web_crawler_expert",
            "ui_design_expert",
            "database_diagnostics_expert",
            "pareto_code_craftsman",
        ):
            return "engineering"
        if template_id in (
            "office_document_assistant",
            "official_document_assistant",
            "office_delivery_blueprint",
            "hr_recruiter",
            "financial_analyst",
            "growth_operator",
            "admin_specialist",
            "competitor_analyst",
            "persona_distiller",
        ):
            return "office"
        if template_id in ("storefront_shopper_agent", "backoffice_merchant_agent"):
            return "commerce"
        return "general"

    @classmethod
    async def _instantiate_individual_internal(
        cls,
        data: dict[str, Any],
        options: CloneTemplateOptions,
    ) -> dict[str, Any]:
        prebuilt_skills = data.pop("prebuilt_skill_ids", [])
        await ensure_skills_enabled(prebuilt_skills, options.template_id)

        name = options.custom_name or resolve_i18n(data.get("name"), options.accept_language) or options.template_id
        description = (
            resolve_i18n(data.get("description"), options.accept_language) if data.get("description") else None
        )

        data["name"] = name
        data["description"] = description
        data["is_built_in"] = False

        if "skill_ids" not in data:
            data["skill_ids"] = []
        for sid in prebuilt_skills:
            if sid not in data["skill_ids"]:
                data["skill_ids"].append(sid)

        for drop_field in ("members", "use_cases", "category"):
            data.pop(drop_field, None)

        agent_dto = AgentCreate.model_validate(data)
        agent = await AgentService.create_agent(agent_dto)
        return {
            "id": agent.id,
            "name": agent.name,
            "agent_type": "individual",
            "template_id": options.template_id,
            "wiki_blueprint_initialized": options.init_wiki_blueprint,
        }

    @classmethod
    async def _instantiate_team_internal(
        cls,
        data: dict[str, Any],
        options: CloneTemplateOptions,
    ) -> dict[str, Any]:
        members_spec: list[dict[str, Any]] = data.get("members", [])
        if not members_spec:
            raise ValueError("Team template must define at least one member")

        all_skills: list[str] = data.get("prebuilt_skill_ids", [])
        for m in members_spec:
            all_skills.extend(m.get("prebuilt_skill_ids", []))
        await ensure_skills_enabled(list(dict.fromkeys(all_skills)), options.template_id)

        created_member_ids: list[str] = []
        try:
            for member in members_spec:
                m_payload = {
                    "name": resolve_i18n(member.get("name"), options.accept_language),
                    "description": (
                        resolve_i18n(member.get("description"), options.accept_language)
                        if member.get("description")
                        else None
                    ),
                    "system_prompt": member.get("system_prompt", ""),
                    "agent_type": "individual",
                    "is_built_in": False,
                    "allow_discovery": False,
                    "prompt_mode": member.get("prompt_mode", "full"),
                    "personality_style": member.get("personality_style", "professional"),
                }
                m_agent = await AgentService.create_agent(AgentCreate.model_validate(m_payload))
                created_member_ids.append(m_agent.id)

            leader_name = (
                options.custom_name or resolve_i18n(data.get("name"), options.accept_language) or options.template_id
            )
            leader_payload = {
                "name": leader_name,
                "description": (
                    resolve_i18n(data.get("description"), options.accept_language) if data.get("description") else None
                ),
                "system_prompt": data.get("system_prompt", ""),
                "agent_type": "team",
                "is_built_in": False,
                "subagent_ids": created_member_ids,
                "allow_discovery": data.get("allow_discovery", True),
                "prompt_mode": data.get("prompt_mode", "full"),
                "personality_style": data.get("personality_style", "professional"),
            }
            leader_agent = await AgentService.create_agent(AgentCreate.model_validate(leader_payload))
            return {
                "id": leader_agent.id,
                "name": leader_agent.name,
                "agent_type": "team",
                "team_member_ids": created_member_ids,
                "template_id": options.template_id,
                "wiki_blueprint_initialized": options.init_wiki_blueprint,
            }
        except Exception:
            for aid in reversed(created_member_ids):
                try:
                    await AgentService.delete_agent(aid)
                except Exception as rollback_err:
                    logger.error("Rollback failed for %s: %s", aid, rollback_err)
            raise
