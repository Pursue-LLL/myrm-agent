"""Agent tool for scheduled task management.

Single ``cron_manage`` tool with implicit schedule detection:
fill ``cron_expr`` → cron, ``every_minutes`` → interval, ``at`` → one-shot.

Includes a ContextVar-based self-scheduling guard that blocks ``add``/``update``
when called from within a cron job execution, preventing infinite task chains.

This file declares the tool and resolves a blueprint and the CSV parameters; parsing of
the tool parameters lives in ``cron_agent_params.py`` and the per-action work in
``cron_agent_actions.py``.

[INPUT]
- toolkits.cron._cron_tool_description::resolve_cron_tool_description (POS: cron_manage_tool 提示词 SSOT 与多语言描述解析)
- toolkits.cron.blueprint_job_spec::BlueprintFiller, BlueprintJobSpec (POS: blueprint 产出的完整 job 定义)
- toolkits.cron.cron_agent_actions::BlueprintCatalogProvider, DeliveryResolver, _do_add, _do_blueprints, _do_list, _do_pause, _do_remove, _do_resume, _do_run, _do_update (POS: cron_manage_tool 各 action 的实现)
- toolkits.cron.cron_agent_params::_parse_csv_tuple (POS: cron_manage_tool 参数解析与校验)
- toolkits.cron.types::DeliveryConfig (POS: cron 数据模型)

[OUTPUT]
- enter_cron_execution_context: Mark the current async context as running inside a cron job execution.
- exit_cron_execution_context: Restore the previous cron execution context.
- create_cron_tools: Create cron_manage_tool with on-demand blueprints (a filled blueprint creates the job it defines, every field forwarded), default_delivery, reminder jobs, locale-aware descriptions.

[POS]
Agent tool for scheduled task management: the ``cron_manage`` tool declaration, the cron-execution guard and blueprint / CSV argument resolution.
"""

from __future__ import annotations

import json
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Literal

from langchain_core.tools import BaseTool, tool

from myrm_agent_harness.toolkits.cron._cron_tool_description import (
    resolve_cron_tool_description,
)
from myrm_agent_harness.toolkits.cron.blueprint_job_spec import (
    BlueprintFiller,
    BlueprintJobSpec,
)
from myrm_agent_harness.toolkits.cron.cron_agent_actions import (
    BlueprintCatalogProvider,
    DeliveryResolver,
    _do_add,
    _do_blueprints,
    _do_list,
    _do_pause,
    _do_remove,
    _do_resume,
    _do_run,
    _do_update,
)
from myrm_agent_harness.toolkits.cron.cron_agent_params import _parse_csv_tuple
from myrm_agent_harness.toolkits.cron.types import DeliveryConfig

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.manager import CronManager

_IN_CRON_EXECUTION: ContextVar[bool] = ContextVar("_in_cron_execution", default=False)
_CRON_EXECUTION_MUTATING_ACTIONS = frozenset({"add", "update", "remove", "run", "pause", "resume"})


def enter_cron_execution_context() -> Token[bool]:
    """Mark the current async context as running inside a cron job callback.

    Returns a token for ``exit_cron_execution_context``.
    """
    return _IN_CRON_EXECUTION.set(True)


def exit_cron_execution_context(token: Token[bool]) -> None:
    """Restore the previous cron execution context."""
    _IN_CRON_EXECUTION.reset(token)


def create_cron_tools(
    manager: CronManager,
    user_id: str,
    *,
    current_model: str = "",
    chat_id: str | None = None,
    agent_id: str | None = None,
    blueprint_filler: BlueprintFiller | None = None,
    blueprint_catalog_provider: BlueprintCatalogProvider | None = None,
    delivery_resolver: DeliveryResolver | None = None,
    default_delivery: DeliveryConfig | None = None,
    description_locale: str | None = None,
) -> list[BaseTool]:
    """Create a single cron management tool bound to a user.

    ``current_model`` is the model name of the calling Agent session,
    used as default when the user doesn't specify a model for a new cron job.

    ``blueprint_catalog_provider`` returns blueprint catalog text for the
    on-demand ``action=blueprints`` lookup (not injected into Turn1 schema).

    ``blueprint_filler`` fills a blueprint by ID and slot values, returning the
    complete ``BlueprintJobSpec`` of the job it defines, or None if unknown.

    ``default_delivery`` is used when ``webhook_url`` is empty instead of
    falling back to in-chat delivery (e.g. IM channel + recipient binding).

    ``delivery_resolver`` maps webhook URLs to ``DeliveryConfig``. When omitted,
    non-empty URLs use generic ``webhook`` delivery (no channel-specific heuristics).

    ``description_locale`` selects the BCP-47 locale for LLM-facing tool description.
    """

    def _resolve_delivery(webhook_url: str) -> DeliveryConfig:
        if delivery_resolver is not None:
            return delivery_resolver(webhook_url)
        if not webhook_url.strip():
            if default_delivery is not None:
                return default_delivery
            return DeliveryConfig(channel="chat")
        return DeliveryConfig(channel="webhook", target=webhook_url)

    tool_description = resolve_cron_tool_description(description_locale)

    @tool("cron_manage_tool", description=tool_description)
    async def cron_manage(
        action: Literal["add", "list", "update", "remove", "run", "pause", "resume", "blueprints"],
        prompt: str = "",
        command: str = "",
        model: str = "",
        cron_expr: str = "",
        every_minutes: int = 0,
        at: str = "",
        tz: str = "",
        job_id: str = "",
        name: str = "",
        name_filter: str = "",
        webhook_url: str = "",
        failure_webhook_url: str = "",
        recurring_confirmed: bool = False,
        active_start: str = "",
        active_end: str = "",
        active_tz: str = "",
        max_fires: int = 0,
        expires_after: str = "",
        context_from: str = "",
        blueprint: str = "",
        blueprint_values: str = "",
        monitor_type: str = "",
        monitor_enabled: bool = False,
        session_mode: str = "",
        stream_url: str = "",
        stream_protocol: str = "",
        stream_filter_json_path: str = "",
        stream_filter_regex: str = "",
        stream_headers: str = "",
        poll_url: str = "",
        poll_json_path: str = "",
        poll_interval_seconds: int = 0,
        reminder: bool = False,
        required_capabilities: str = "",
        tools_allowed: str = "",
        skill_ids: str = "",
    ) -> str:
        effective_model = model.strip() or current_model

        if action in _CRON_EXECUTION_MUTATING_ACTIONS and _IN_CRON_EXECUTION.get():
            return (
                "Error: cannot create or modify scheduled tasks from within "
                "a cron job execution. This prevents infinite task chains."
            )

        # Blueprint-based creation: the filler returns the whole job definition
        spec: BlueprintJobSpec | None = None
        if action == "add" and blueprint.strip() and blueprint_filler:
            bp_values: dict[str, str] = {}
            if blueprint_values.strip():
                try:
                    bp_values = json.loads(blueprint_values)
                except (json.JSONDecodeError, TypeError):
                    return 'Error: blueprint_values must be valid JSON object, e.g. \'{"time": "08:00"}\'.'

            spec = blueprint_filler(blueprint.strip(), bp_values, tz.strip() or None)
            if spec is None:
                return f"Error: unknown blueprint '{blueprint.strip()}'. Use list action or check available blueprints."

        effective_required_capabilities = (
            _parse_csv_tuple(required_capabilities)
            if required_capabilities.strip()
            else (spec.required_capabilities if spec else ())
        )
        effective_tools_allowed = (
            _parse_csv_tuple(tools_allowed) if tools_allowed.strip() else (spec.tools_allowed if spec else None)
        )
        effective_skill_ids = _parse_csv_tuple(skill_ids) if skill_ids.strip() else (spec.skill_ids if spec else ())

        dispatch = {
            "add": lambda: _do_add(
                mgr=manager,
                user_id=user_id,
                prompt=spec.prompt if spec else prompt,
                command=command,
                model=effective_model,
                cron_expr=cron_expr,
                every_minutes=every_minutes,
                at=at,
                tz=tz,
                name=name or (spec.name if spec else ""),
                webhook_url=webhook_url,
                failure_webhook_url=failure_webhook_url,
                recurring_confirmed=recurring_confirmed,
                active_start=active_start,
                active_end=active_end,
                active_tz=active_tz,
                chat_id=chat_id,
                max_fires=max_fires,
                expires_after=expires_after,
                agent_id=agent_id,
                context_from=context_from,
                monitor_type=monitor_type,
                monitor_enabled=monitor_enabled,
                session_mode=session_mode,
                stream_url=stream_url,
                stream_protocol=stream_protocol,
                stream_filter_json_path=stream_filter_json_path,
                stream_filter_regex=stream_filter_regex,
                stream_headers=stream_headers,
                poll_url=poll_url,
                poll_json_path=poll_json_path,
                poll_interval_seconds=poll_interval_seconds,
                reminder=reminder,
                required_capabilities=effective_required_capabilities,
                tools_allowed=effective_tools_allowed,
                skill_ids=effective_skill_ids,
                spec=spec,
                resolve_delivery=_resolve_delivery,
            ),
            "list": lambda: _do_list(manager, user_id, name_filter),
            "blueprints": lambda: _do_blueprints(blueprint_catalog_provider),
            "update": lambda: _do_update(
                manager,
                user_id,
                job_id,
                prompt,
                command,
                model,
                cron_expr,
                every_minutes,
                at,
                tz,
                name,
                max_fires,
                expires_after,
                context_from=context_from,
                monitor_type=monitor_type,
                monitor_enabled=monitor_enabled,
                session_mode=session_mode,
                required_capabilities=_parse_csv_tuple(required_capabilities)
                if required_capabilities.strip()
                else None,
                tools_allowed=tuple(_parse_csv_tuple(tools_allowed)) if tools_allowed.strip() else None,
                skill_ids=tuple(_parse_csv_tuple(skill_ids)) if skill_ids.strip() else None,
            ),
            "remove": lambda: _do_remove(manager, user_id, job_id),
            "run": lambda: _do_run(manager, user_id, job_id),
            "pause": lambda: _do_pause(manager, user_id, job_id),
            "resume": lambda: _do_resume(manager, user_id, job_id),
        }
        handler = dispatch.get(action)
        if not handler:
            return f"Unknown action: {action}"
        return await handler()

    return [cron_manage]
