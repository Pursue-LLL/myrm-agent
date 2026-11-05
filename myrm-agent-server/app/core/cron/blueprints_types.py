"""Cron 蓝图的数据结构与调度辅助。

[POS]
蓝图目录（blueprints_*）与注册表（blueprints.py）共用的类型和纯函数；不包含任何具体蓝图。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.core.cron.blueprint_i18n_supplement import SUPPLEMENTAL_BY_ID


class BlueprintFillError(ValueError):
    """Raised when blueprint slot values fail validation."""


@dataclass(frozen=True, slots=True)
class BlueprintSlot:
    """A user-fillable parameter in a blueprint."""

    name: str
    type: Literal["time", "text", "enum"]
    label: str
    default: str
    options: tuple[str, ...] = ()
    optional: bool = False


@dataclass(frozen=True, slots=True)
class BlueprintScheduleResult:
    """Generated schedule from blueprint slot values."""

    kind: Literal["cron", "interval", "once"]
    expr: str | None = None
    tz: str | None = None
    interval_ms: int | None = None


@dataclass(frozen=True, slots=True)
class BlueprintFillResult:
    """Result of filling a blueprint with user-provided slot values."""

    schedule: BlueprintScheduleResult
    prompt: str
    name: str
    required_capabilities: tuple[str, ...] = ()
    tools_allowed: tuple[str, ...] | None = None
    skill_ids: tuple[str, ...] = ()
    job_type: Literal["agent", "shell", "router", "reminder"] = "agent"
    session_target: Literal["isolated", "main", "daily"] = "isolated"
    deduplicate: bool = False
    skip_if_active: bool = False
    timeout_seconds: int | None = None
    monitor_config: "BlueprintMonitorDefaults | None" = None
    failure_alert: "BlueprintFailureAlertDefaults | None" = None
    pre_condition_script: str | None = None
    command: str | None = None


@dataclass(frozen=True, slots=True)
class BlueprintMonitorDefaults:
    """Default monitor configuration to apply when creating a job from a blueprint."""

    monitor_type: Literal["set", "hash"] = "set"
    ttl_days: int = 30
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class BlueprintFailureAlertDefaults:
    """Default failure-alert policy to apply when creating a job from a blueprint."""

    enabled: bool = True
    after: int = 3
    cooldown_seconds: int = 300


@dataclass(frozen=True, slots=True)
class BlueprintJobDefaults:
    """Execution defaults used to materialize a full Cron create payload."""

    job_type: Literal["agent", "shell", "router", "reminder"] = "agent"
    session_target: Literal["isolated", "main", "daily"] = "isolated"
    deduplicate: bool = False
    skip_if_active: bool = False
    timeout_seconds: int | None = None
    monitor_config: BlueprintMonitorDefaults | None = None
    failure_alert: BlueprintFailureAlertDefaults | None = None
    pre_condition_script_template: dict[str, str] | None = None
    command: str | None = None


@dataclass(frozen=True, slots=True)
class CronBlueprint:
    """A reusable automation template."""

    id: str
    icon: str
    title: dict[str, str]
    description: dict[str, str]
    prompt_template: dict[str, str]
    slots: tuple[BlueprintSlot, ...]
    category: str = "general"
    tags: tuple[str, ...] = ()
    sort_order: int = 0
    default_required_capabilities: tuple[str, ...] = ()
    default_tools_allowed: tuple[str, ...] | None = None
    default_skill_ids: tuple[str, ...] = ()
    job_defaults: BlueprintJobDefaults = field(default_factory=BlueprintJobDefaults)
    _schedule_builder: str = field(default="", repr=False)


_CAP_WEB = ("web_search_tool", "net_fetch")
_TOOLS_WEB = ("web_search",)
_CAP_RESEARCH = ("web_search_tool", "net_fetch", "file_read")
_CAP_RESEARCH_SAVE = (*_CAP_RESEARCH, "file_write")
_TOOLS_RESEARCH = ("web_search", "file_ops")
_CAP_DEVOPS = ("shell_exec", "file_read", "file_write", "code_interpreter")
_TOOLS_DEVOPS = ("web_search", "file_ops", "code_execute")
# wiki_query_tool / wiki_apply_tool are gated by knowledge_* permissions, the raw/ scan by file_read.
_CAP_WIKI = ("file_read", "knowledge_read", "knowledge_write")
_TOOLS_WIKI = ("wiki", "memory", "file_ops")
_ASSET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_QUOTE_CURRENCY_RE = re.compile(r"^[a-z0-9]{2,10}$")


def _merge_locale_dict(base: dict[str, str], extra: dict[str, str]) -> dict[str, str]:
    merged = dict(base)
    merged.update(extra)
    return merged


def _with_supplemental_locales(bp: CronBlueprint) -> CronBlueprint:
    """Attach ja/de/ko catalog fields from the supplemental locale module."""
    supplement = SUPPLEMENTAL_BY_ID.get(bp.id)
    if supplement is None:
        return bp
    return CronBlueprint(
        id=bp.id,
        icon=bp.icon,
        title=_merge_locale_dict(bp.title, supplement["title"]),
        description=_merge_locale_dict(bp.description, supplement["description"]),
        prompt_template=_merge_locale_dict(bp.prompt_template, supplement["prompt_template"]),
        slots=bp.slots,
        category=bp.category,
        tags=bp.tags,
        sort_order=bp.sort_order,
        default_required_capabilities=bp.default_required_capabilities,
        default_tools_allowed=bp.default_tools_allowed,
        default_skill_ids=bp.default_skill_ids,
        job_defaults=bp.job_defaults,
        _schedule_builder=bp._schedule_builder,
    )


def _time_to_cron(time_str: str) -> str:
    parts = time_str.split(":")
    h, m = int(parts[0]), int(parts[1])
    return f"{m} {h} * * *"


def _time_to_cron_weekday(time_str: str, day: str) -> str:
    parts = time_str.split(":")
    h, m = int(parts[0]), int(parts[1])
    return f"{m} {h} * * {day}"


def _time_to_cron_with_weekdays(time_str: str, weekdays: str) -> str:
    parts = time_str.split(":")
    h, m = int(parts[0]), int(parts[1])
    dow = "1-5" if weekdays == "weekdays" else ("0,6" if weekdays == "weekends" else "*")
    return f"{m} {h} * * {dow}"
