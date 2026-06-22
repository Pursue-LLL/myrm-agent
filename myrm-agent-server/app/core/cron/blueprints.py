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
- CronBlueprint: Single blueprint definition dataclass.
- BUILTIN_BLUEPRINTS: Registry of all built-in blueprints.
- fill_blueprint: Fills a blueprint with slot values, returning schedule + prompt.

[POS]
Cron blueprint single-source-of-truth definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class BlueprintSlot:
    """A user-fillable parameter in a blueprint."""

    name: str
    type: Literal["time", "text", "enum"]
    label: str
    default: str
    options: tuple[str, ...] = ()


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
    _schedule_builder: str = field(default="", repr=False)


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


BUILTIN_BLUEPRINTS: tuple[CronBlueprint, ...] = (
    CronBlueprint(
        id="morning_briefing",
        icon="Sun",
        title={"en": "Morning Briefing", "zh": "每日早报"},
        description={
            "en": "Get a daily briefing on topics you care about",
            "zh": "每天获取你关心的话题简报",
        },
        prompt_template={
            "en": (
                "Provide a concise morning briefing covering: key news headlines, "
                "weather outlook, and any important reminders for today. "
                "Keep it brief and actionable."
            ),
            "zh": (
                "提供一份简洁的早间简报，涵盖：重要新闻头条、天气预报、"
                "以及今天的重要提醒事项。保持简短且可操作。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="08:00"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="everyday",
                options=("everyday", "weekdays", "weekends"),
            ),
        ),
        category="productivity",
        tags=("daily", "news", "briefing"),
        sort_order=0,
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="weekly_review",
        icon="ClipboardList",
        title={"en": "Weekly Review", "zh": "每周回顾"},
        description={
            "en": "Summarize weekly progress and plan ahead",
            "zh": "总结每周进展并规划下周",
        },
        prompt_template={
            "en": (
                "Conduct a comprehensive weekly review: summarize key accomplishments, "
                "identify blockers or challenges faced, and suggest priorities for "
                "the upcoming week. Organize by category."
            ),
            "zh": (
                "进行一次全面的每周回顾：总结本周关键成果、"
                "识别遇到的阻碍或挑战，并建议下周的优先事项。按类别组织。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="18:00"),
            BlueprintSlot(
                name="day",
                type="enum",
                label="day",
                default="5",
                options=("1", "2", "3", "4", "5", "6", "0"),
            ),
        ),
        category="productivity",
        tags=("weekly", "review", "planning"),
        sort_order=1,
        _schedule_builder="time_weekday",
    ),
    CronBlueprint(
        id="custom_reminder",
        icon="Bell",
        title={"en": "Custom Reminder", "zh": "自定义提醒"},
        description={
            "en": "Set a recurring reminder with your own message",
            "zh": "设置一个自定义消息的定期提醒",
        },
        prompt_template={
            "en": "Remind me: {message}",
            "zh": "提醒我：{message}",
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="09:00"),
            BlueprintSlot(name="message", type="text", label="message", default=""),
        ),
        category="personal",
        tags=("reminder", "custom"),
        sort_order=2,
        _schedule_builder="time_daily",
    ),
    CronBlueprint(
        id="news_digest",
        icon="Newspaper",
        title={"en": "News Digest", "zh": "新闻摘要"},
        description={
            "en": "Get a curated digest on your chosen topics",
            "zh": "获取你选择的话题的精选摘要",
        },
        prompt_template={
            "en": (
                "Search the web and compile a concise digest of the latest news and "
                "developments about: {topic}. Include 3-5 key items with brief summaries. "
                "Prioritize breaking news and significant developments."
            ),
            "zh": (
                "搜索网络并编制一份关于以下话题的最新新闻和发展的精简摘要：{topic}。"
                "包含 3-5 个关键条目并附简短摘要。优先报道突发新闻和重大进展。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="07:30"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="everyday",
                options=("everyday", "weekdays", "weekends"),
            ),
            BlueprintSlot(
                name="topic",
                type="text",
                label="topic",
                default="AI and technology",
            ),
        ),
        category="information",
        tags=("news", "digest", "topics"),
        sort_order=3,
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="evening_winddown",
        icon="Moon",
        title={"en": "Evening Wind-down", "zh": "晚间放松"},
        description={
            "en": "End your day with a calming summary and tomorrow's preview",
            "zh": "以平静的总结和明日预览结束一天",
        },
        prompt_template={
            "en": (
                "Provide a calming evening summary: briefly recap today's highlights, "
                "preview tomorrow's schedule and priorities, and offer a relaxation tip "
                "or inspirational thought for the evening."
            ),
            "zh": (
                "提供一份平和的晚间总结：简要回顾今天的亮点、"
                "预览明天的日程和优先事项，并提供一条放松建议或晚间灵感语录。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="21:00"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="everyday",
                options=("everyday", "weekdays", "weekends"),
            ),
        ),
        category="personal",
        tags=("evening", "relaxation", "summary"),
        sort_order=4,
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="local_health_check",
        icon="Activity",
        title={"en": "Local Health Check", "zh": "本地健康巡检"},
        description={
            "en": "Monitor your system's CPU, memory, and disk status",
            "zh": "监控系统 CPU、内存和磁盘状态",
        },
        prompt_template={
            "en": (
                "Check the current system health status. Report CPU usage, memory usage, "
                "disk space remaining, and any services that appear to be down or unhealthy. "
                "Only report issues that need attention — if everything is normal, keep it brief."
            ),
            "zh": (
                "检查当前系统健康状态。报告 CPU 使用率、内存使用率、"
                "剩余磁盘空间，以及任何似乎宕机或不健康的服务。"
                "只报告需要关注的问题——如果一切正常，请保持简短。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="09:00"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="everyday",
                options=("everyday", "weekdays", "weekends"),
            ),
        ),
        category="devops",
        tags=("health", "monitoring", "system", "local"),
        sort_order=5,
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="competitor_watch",
        icon="Eye",
        title={"en": "Competitor Watch", "zh": "竞品动态监控"},
        description={
            "en": "Track competitor news and product updates weekly",
            "zh": "每周追踪竞品新闻和产品更新",
        },
        prompt_template={
            "en": (
                "Search the web for the latest news, product updates, and announcements from: "
                "{competitors}. Compile a concise competitive intelligence brief covering: "
                "new features, pricing changes, partnerships, funding, and notable blog posts. "
                "Highlight items that may impact our strategy."
            ),
            "zh": (
                "搜索以下竞品的最新新闻、产品更新和公告：{competitors}。"
                "编制一份简洁的竞争情报简报，涵盖：新功能、定价变化、合作伙伴关系、"
                "融资动态和值得注意的博客文章。突出可能影响我们战略的条目。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="09:00"),
            BlueprintSlot(
                name="day",
                type="enum",
                label="day",
                default="1",
                options=("1", "2", "3", "4", "5", "6", "0"),
            ),
            BlueprintSlot(
                name="competitors",
                type="text",
                label="competitors",
                default="",
            ),
        ),
        category="business",
        tags=("competitor", "intelligence", "weekly", "research"),
        sort_order=6,
        _schedule_builder="time_weekday",
    ),
    CronBlueprint(
        id="habit_checkin",
        icon="CheckSquare",
        title={"en": "Habit Check-in", "zh": "习惯打卡"},
        description={
            "en": "Daily reminder to track your habits and routines",
            "zh": "每日提醒追踪你的习惯和日常",
        },
        prompt_template={
            "en": (
                "It's time for your daily habit check-in! Ask me about my progress on: "
                "{habits}. Provide encouragement and track my streak. "
                "If I've missed any, offer a gentle reminder without judgment."
            ),
            "zh": (
                "是时候进行每日习惯打卡了！询问我在以下方面的进展：{habits}。"
                "给予鼓励并追踪我的连续完成情况。"
                "如果我遗漏了任何一项，请温和地提醒，不要评判。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="21:00"),
            BlueprintSlot(
                name="habits",
                type="text",
                label="habits",
                default="exercise, reading, meditation",
            ),
        ),
        category="personal",
        tags=("habit", "tracking", "daily", "wellness"),
        sort_order=7,
        _schedule_builder="time_daily",
    ),
    CronBlueprint(
        id="learn_daily",
        icon="BookOpen",
        title={"en": "Daily Learning", "zh": "每日学习"},
        description={
            "en": "Get a curated learning topic delivered daily",
            "zh": "每天获得一个精选学习主题",
        },
        prompt_template={
            "en": (
                "Teach me something interesting and useful about: {subject}. "
                "Explain one concept, technique, or recent development in 2-3 paragraphs. "
                "Include a practical example or exercise I can try. "
                "Make it accessible but not superficial."
            ),
            "zh": (
                "教我一些关于以下主题的有趣且有用的知识：{subject}。"
                "用 2-3 段解释一个概念、技术或近期发展。"
                "包含一个我可以尝试的实际例子或练习。"
                "内容要易懂但不肤浅。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="08:30"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="weekdays",
                options=("everyday", "weekdays", "weekends"),
            ),
            BlueprintSlot(
                name="subject",
                type="text",
                label="subject",
                default="programming and software architecture",
            ),
        ),
        category="education",
        tags=("learning", "education", "daily", "growth"),
        sort_order=8,
        _schedule_builder="time_weekdays",
    ),
)

_BLUEPRINT_MAP: dict[str, CronBlueprint] = {bp.id: bp for bp in BUILTIN_BLUEPRINTS}


def get_blueprint(blueprint_id: str) -> CronBlueprint | None:
    """Look up a blueprint by ID."""
    return _BLUEPRINT_MAP.get(blueprint_id)


def fill_blueprint(
    blueprint_id: str,
    values: dict[str, str],
    *,
    locale: str = "en",
    tz: str | None = None,
) -> BlueprintFillResult | None:
    """Fill a blueprint's slots and produce schedule + prompt.

    Returns None if blueprint_id is unknown.
    """
    bp = get_blueprint(blueprint_id)
    if not bp:
        return None

    effective_values: dict[str, str] = {}
    for slot in bp.slots:
        effective_values[slot.name] = values.get(slot.name, slot.default)

    schedule = _build_schedule_from_blueprint(bp, effective_values, tz)
    prompt = _build_prompt_from_blueprint(bp, effective_values, locale)
    name = prompt[:40] if len(prompt) > 40 else prompt

    return BlueprintFillResult(schedule=schedule, prompt=prompt, name=name)


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
    except (KeyError, IndexError):
        return template


def get_blueprints_for_tool_description(locale: str = "en") -> str:
    """Generate a concise blueprint catalog for injection into the cron_manage tool description.

    Kept short to avoid bloating the tool schema and harming prompt cache.
    """
    lines: list[str] = ["Available blueprints (use blueprint param for pre-tuned prompts):"]
    for bp in BUILTIN_BLUEPRINTS:
        lang = locale if locale in bp.title else "en"
        title = bp.title.get(lang, bp.title.get("en", bp.id))
        slot_names = ", ".join(s.name for s in bp.slots)
        lines.append(f'  - "{bp.id}": {title} (slots: {slot_names})')
    return "\n".join(lines)
