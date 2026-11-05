"""Cron job blueprint definitions — single source of truth.

Blueprints provide pre-configured templates for common recurring tasks.
They define slots (user-fillable parameters), schedule generation logic,
and high-quality prompt templates.

Both the frontend and the Agent tool consume these definitions via the
``/cron/blueprints`` API endpoint, ensuring GUI-created and Agent-created
tasks use identical, professionally tuned prompts and schedules.

[INPUT]
- (none)

[OUTPUT]
- BlueprintSlot: Slot schema with optional flag for non-required text fields.
- CronBlueprint: Single blueprint definition dataclass.
- BUILTIN_BLUEPRINTS: Registry of all built-in blueprints.
- BlueprintFillError: Slot validation error for fill operations.
- fill_blueprint: Fills a blueprint with slot values; name from title[locale]; validates required text slots (optional slots may be empty).

[POS]
Cron blueprint single-source-of-truth definitions.
"""

from __future__ import annotations

from app.core.cron.blueprints.catalog.daily import BLUEPRINTS as _DAILY
from app.core.cron.blueprints.catalog.finance import BLUEPRINTS as _FINANCE
from app.core.cron.blueprints.catalog.knowledge import BLUEPRINTS as _KNOWLEDGE
from app.core.cron.blueprints.catalog.marketing import BLUEPRINTS as _MARKETING
from app.core.cron.blueprints.core.types import (
    _ASSET_ID_RE,
    _QUOTE_CURRENCY_RE,
    BlueprintFailureAlertDefaults,
    BlueprintFillError,
    BlueprintFillResult,
    BlueprintMonitorDefaults,
    BlueprintScheduleResult,
    BlueprintSlot,
    CronBlueprint,
    _time_to_cron,
    _time_to_cron_weekday,
    _time_to_cron_with_weekdays,
    _with_supplemental_locales,
)

__all__ = [
    "BUILTIN_BLUEPRINTS",
    "BlueprintFailureAlertDefaults",
    "BlueprintFillError",
    "BlueprintFillResult",
    "BlueprintMonitorDefaults",
    "BlueprintScheduleResult",
    "BlueprintSlot",
    "CronBlueprint",
    "fill_blueprint",
    "get_blueprint",
    "get_blueprints_for_tool_description",
]

_RAW_BUILTIN_BLUEPRINTS: tuple[CronBlueprint, ...] = (*_DAILY, *_FINANCE, *_KNOWLEDGE, *_MARKETING)

BUILTIN_BLUEPRINTS: tuple[CronBlueprint, ...] = tuple(_with_supplemental_locales(bp) for bp in _RAW_BUILTIN_BLUEPRINTS)

_BLUEPRINT_MAP: dict[str, CronBlueprint] = {bp.id: bp for bp in BUILTIN_BLUEPRINTS}


def get_blueprint(blueprint_id: str) -> CronBlueprint | None:
    """Look up a blueprint by ID."""
    return _BLUEPRINT_MAP.get(blueprint_id)


def _resolve_locale_title(bp: CronBlueprint, locale: str) -> str:
    lang = locale if locale in bp.title else "en"
    return bp.title.get(lang, bp.title.get("en", bp.id))


def _validate_slot_values(bp: CronBlueprint, values: dict[str, str]) -> dict[str, str]:
    """Resolve and validate user slot values against the blueprint schema."""
    known = {slot.name for slot in bp.slots}
    unknown = sorted(set(values) - known)
    if unknown:
        raise BlueprintFillError(f"unknown slot(s): {', '.join(unknown)} — valid: {', '.join(sorted(known))}")

    effective: dict[str, str] = {}
    for slot in bp.slots:
        raw = values.get(slot.name, slot.default)
        if slot.type == "text" and slot.default == "" and not str(raw).strip() and not slot.optional:
            raise BlueprintFillError(f"missing required value: {slot.name} ({slot.label})")
        if slot.type == "enum" and slot.options and str(raw) not in slot.options:
            raise BlueprintFillError(f"{slot.name}={raw!r} not allowed — one of {', '.join(slot.options)}")
        effective[slot.name] = str(raw)
    return effective


def fill_blueprint(
    blueprint_id: str | CronBlueprint,
    values: dict[str, str],
    *,
    locale: str = "en",
    tz: str | None = None,
) -> BlueprintFillResult | None:
    """Fill a blueprint's slots and produce schedule + prompt.

    Returns None if blueprint_id is unknown.
    Raises BlueprintFillError when slot values are invalid.
    """
    if isinstance(blueprint_id, CronBlueprint):
        bp: CronBlueprint | None = blueprint_id
    else:
        bp = get_blueprint(blueprint_id)
    if not bp:
        return None

    effective_values = _validate_slot_values(bp, values)

    schedule = _build_schedule_from_blueprint(bp, effective_values, tz)
    prompt = _build_prompt_from_blueprint(bp, effective_values, locale)
    pre_condition_script = _build_pre_condition_script(bp, effective_values, locale)
    name = _resolve_locale_title(bp, locale)[:40]
    defaults = bp.job_defaults

    command = defaults.command
    if bp.id == "wiki_maintain":
        mode = effective_values.get("mode", "structural")
        if mode not in ("structural", "full"):
            raise BlueprintFillError(f"mode={mode!r} not allowed — one of structural, full")
        command = f"__wiki_maintain__:{mode}"

    return BlueprintFillResult(
        schedule=schedule,
        prompt=prompt,
        name=name,
        required_capabilities=bp.default_required_capabilities,
        tools_allowed=bp.default_tools_allowed,
        skill_ids=bp.default_skill_ids,
        job_type=defaults.job_type,
        session_target=defaults.session_target,
        deduplicate=defaults.deduplicate,
        skip_if_active=defaults.skip_if_active,
        timeout_seconds=defaults.timeout_seconds,
        monitor_config=defaults.monitor_config,
        failure_alert=defaults.failure_alert,
        pre_condition_script=pre_condition_script,
        command=command,
    )


def _build_schedule_from_blueprint(
    bp: CronBlueprint,
    values: dict[str, str],
    tz: str | None,
) -> BlueprintScheduleResult:
    """Generate a schedule based on the blueprint's builder type."""
    time_val = values.get("time", "08:00")
    builder = bp._schedule_builder

    if builder == "time_weekdays":
        weekdays_val = values.get("weekdays", "everyday")
        expr = _time_to_cron_with_weekdays(time_val, weekdays_val)
    elif builder == "time_weekday":
        day_val = values.get("day", "5")
        expr = _time_to_cron_weekday(time_val, day_val)
    elif builder == "time_daily":
        expr = _time_to_cron(time_val)
    else:
        expr = _time_to_cron(time_val)

    return BlueprintScheduleResult(kind="cron", expr=expr, tz=tz)


def _build_prompt_from_blueprint(
    bp: CronBlueprint,
    values: dict[str, str],
    locale: str,
) -> str:
    """Build the prompt by interpolating slot values into the template."""
    lang = locale if locale in bp.prompt_template else "en"
    template = bp.prompt_template.get(lang, bp.prompt_template.get("en", ""))
    try:
        return template.format(**values)
    except KeyError as exc:
        raise BlueprintFillError(f"blueprint prompt missing value for {exc}") from exc


def _escape_for_python_double_quote(value: str) -> str:
    """Escape a string for safe insertion into Python double-quoted literals."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def _parse_positive_number(raw: str, name: str) -> float:
    value = raw.strip()
    try:
        num = float(value)
    except ValueError as exc:
        raise BlueprintFillError(f"{name} must be a number, got {raw!r}") from exc
    if num <= 0:
        raise BlueprintFillError(f"{name} must be > 0, got {raw!r}")
    return num


def _normalize_simple_financial_script_values(values: dict[str, str]) -> dict[str, str]:
    asset = values["asset"].strip().lower()
    if not _ASSET_ID_RE.fullmatch(asset):
        raise BlueprintFillError(f"asset must match [a-z0-9-] and start with alphanumeric (got {values['asset']!r})")

    quote_currency = values["quote_currency"].strip().lower()
    if not _QUOTE_CURRENCY_RE.fullmatch(quote_currency):
        raise BlueprintFillError(f"quote_currency must be alphanumeric (2-10 chars), got {values['quote_currency']!r}")

    lower = _parse_positive_number(values["lower_bound"], "lower_bound")
    upper = _parse_positive_number(values["upper_bound"], "upper_bound")
    if lower >= upper:
        raise BlueprintFillError(f"lower_bound must be less than upper_bound (got {lower:g} >= {upper:g})")

    source = values["source"].strip().lower()
    if source not in {"coingecko", "binance"}:
        raise BlueprintFillError(f"source must be coingecko or binance, got {values['source']!r}")

    return {
        **values,
        "asset": _escape_for_python_double_quote(asset),
        "quote_currency": _escape_for_python_double_quote(quote_currency),
        "lower_bound": f"{lower:g}",
        "upper_bound": f"{upper:g}",
        "source": source,
    }


def _build_pre_condition_script(
    bp: CronBlueprint,
    values: dict[str, str],
    locale: str,
) -> str | None:
    """Build pre-condition script from locale-aware template if configured."""
    templates = bp.job_defaults.pre_condition_script_template
    if not templates:
        return None

    lang = locale if locale in templates else "en"
    template = templates.get(lang, templates.get("en", ""))
    if not template:
        return None

    fmt_values = values
    if bp.id == "financial_monitor_simple":
        fmt_values = _normalize_simple_financial_script_values(values)
    try:
        return template.format(**fmt_values)
    except KeyError as exc:
        raise BlueprintFillError(f"blueprint pre-condition script missing value for {exc}") from exc


def _slot_name_for_tool_description(slot: BlueprintSlot) -> str:
    """Compact optional marker for agent tool catalog (minimal prompt-cache footprint)."""
    return f"{slot.name}?" if slot.optional else slot.name


def get_blueprints_for_tool_description(locale: str = "en") -> str:
    """Generate the concise blueprint catalog returned by the cron_manage ``blueprints`` action.

    Returned on demand as a tool result, never injected into the tool schema, so the prompt cache is unaffected.
    """
    lines: list[str] = ["Available blueprints (use blueprint param for pre-tuned prompts):"]
    for bp in BUILTIN_BLUEPRINTS:
        lang = locale if locale in bp.title else "en"
        title = bp.title.get(lang, bp.title.get("en", bp.id))
        slot_names = ", ".join(_slot_name_for_tool_description(s) for s in bp.slots)
        lines.append(f'  - "{bp.id}": {title} (slots: {slot_names})')
    return "\n".join(lines)
