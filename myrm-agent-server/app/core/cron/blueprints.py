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

from dataclasses import dataclass, field
import re
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
    job_type: Literal["agent", "shell", "router", "reminder"] = "agent"
    session_target: Literal["isolated", "main", "daily"] = "isolated"
    deduplicate: bool = False
    skip_if_active: bool = False
    timeout_seconds: int | None = None
    monitor_config: "BlueprintMonitorDefaults | None" = None
    failure_alert: "BlueprintFailureAlertDefaults | None" = None
    pre_condition_script: str | None = None


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
    job_defaults: BlueprintJobDefaults = field(default_factory=BlueprintJobDefaults)
    _schedule_builder: str = field(default="", repr=False)


_CAP_WEB = ("web_search_tool", "net_fetch")
_TOOLS_WEB = ("web_search",)
_CAP_RESEARCH = ("web_search_tool", "net_fetch", "file_read")
_TOOLS_RESEARCH = ("web_search", "file_ops")
_CAP_DEVOPS = ("shell_exec", "file_read", "file_write", "code_interpreter_tool")
_TOOLS_DEVOPS = ("web_search", "file_ops", "code_execute")
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


_RAW_BUILTIN_BLUEPRINTS: tuple[CronBlueprint, ...] = (
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
        default_required_capabilities=_CAP_RESEARCH,
        default_tools_allowed=_TOOLS_RESEARCH,
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
        default_required_capabilities=_CAP_WEB,
        default_tools_allowed=_TOOLS_WEB,
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
        default_required_capabilities=_CAP_DEVOPS,
        default_tools_allowed=_TOOLS_DEVOPS,
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
        default_required_capabilities=_CAP_RESEARCH,
        default_tools_allowed=_TOOLS_RESEARCH,
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
        default_required_capabilities=_CAP_WEB,
        default_tools_allowed=_TOOLS_WEB,
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="social_media_watch",
        icon="Radio",
        title={"en": "Social Media Watch", "zh": "社媒舆情监控"},
        description={
            "en": "Monitor social media for brand mentions, sentiment shifts, and trending topics",
            "zh": "监控社交媒体上的品牌提及、情感变化和热门话题",
        },
        prompt_template={
            "en": (
                "Monitor the following social media platforms for mentions of: {brand}. "
                "Search using keywords: {keywords}. "
                "Platforms to check: {platforms}. "
                "Collect recent posts (last 24 hours), classify sentiment, identify notable "
                "positive and negative mentions, detect trends, and produce a structured report. "
                "Flag any strongly negative posts that require immediate attention."
            ),
            "zh": (
                "监控以下社交媒体平台上关于 {brand} 的提及。"
                "使用关键词搜索：{keywords}。"
                "需要检查的平台：{platforms}。"
                "收集最近的帖子（过去24小时），分类情感倾向，识别值得关注的正面和负面提及，"
                "检测趋势，并生成结构化报告。标记需要立即关注的强负面帖子。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="09:00"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="weekdays",
                options=("everyday", "weekdays", "weekends"),
            ),
            BlueprintSlot(
                name="brand",
                type="text",
                label="brand",
                default="",
            ),
            BlueprintSlot(
                name="platforms",
                type="text",
                label="platforms",
                default="Xiaohongshu, Weibo",
            ),
            BlueprintSlot(
                name="keywords",
                type="text",
                label="keywords",
                default="",
                optional=True,
            ),
        ),
        category="business",
        tags=("social-media", "monitoring", "sentiment", "brand"),
        sort_order=9,
        default_required_capabilities=_CAP_RESEARCH,
        default_tools_allowed=_TOOLS_RESEARCH,
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="financial_monitor_simple",
        icon="Activity",
        title={"en": "Financial Monitor (Simple)", "zh": "金融监控（简单版）"},
        description={
            "en": "Zero-LLM threshold alert using a Python pre-flight probe",
            "zh": "使用 Python 预检脚本的零 LLM 阈值告警",
        },
        prompt_template={
            "en": (
                "This job runs in router mode. Use the pre-flight probe output as the final message. "
                "If the probe prints [SKIP], stay silent."
            ),
            "zh": (
                "该任务运行在 router 模式。将预检脚本输出作为最终消息。"
                "如果预检脚本输出 [SKIP]，保持静默。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="08:00"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="weekdays",
                options=("everyday", "weekdays", "weekends"),
            ),
            BlueprintSlot(name="asset", type="text", label="asset", default="bitcoin"),
            BlueprintSlot(
                name="quote_currency",
                type="enum",
                label="quote_currency",
                default="usd",
                options=("usd", "usdt", "eur", "cny"),
            ),
            BlueprintSlot(name="lower_bound", type="text", label="lower_bound", default="58000"),
            BlueprintSlot(name="upper_bound", type="text", label="upper_bound", default="68000"),
            BlueprintSlot(
                name="source",
                type="enum",
                label="source",
                default="coingecko",
                options=("coingecko", "binance"),
            ),
        ),
        category="business",
        tags=("finance", "monitoring", "threshold", "low-cost"),
        sort_order=10,
        job_defaults=BlueprintJobDefaults(
            job_type="router",
            session_target="isolated",
            deduplicate=True,
            skip_if_active=True,
            timeout_seconds=90,
            failure_alert=BlueprintFailureAlertDefaults(enabled=True, after=2, cooldown_seconds=900),
            pre_condition_script_template={
                "en": (
                    "import json\n"
                    "import urllib.request\n"
                    "from datetime import datetime, timezone\n"
                    "\n"
                    'asset_id = "{asset}".strip().lower()\n'
                    'vs_currency = "{quote_currency}".strip().lower()\n'
                    'lower_bound = float("{lower_bound}")\n'
                    'upper_bound = float("{upper_bound}")\n'
                    'source = "{source}".strip().lower()\n'
                    "\n"
                    "def _fetch_from_binance() -> float:\n"
                    "    symbol = asset_id.upper() + vs_currency.upper()\n"
                    '    url = "https://api.binance.com/api/v3/ticker/price?symbol=" + symbol\n'
                    "    with urllib.request.urlopen(url, timeout=12) as resp:\n"
                    '        data = json.loads(resp.read().decode("utf-8"))\n'
                    '    return float(data["price"])\n'
                    "\n"
                    "def _fetch_from_coingecko() -> float:\n"
                    '    url = "https://api.coingecko.com/api/v3/simple/price?ids=" + asset_id + "&vs_currencies=" + vs_currency\n'
                    "    with urllib.request.urlopen(url, timeout=12) as resp:\n"
                    '        data = json.loads(resp.read().decode("utf-8"))\n'
                    "    if asset_id not in data or vs_currency not in data[asset_id]:\n"
                    '        raise RuntimeError("No quote returned for " + asset_id + "/" + vs_currency)\n'
                    "    return float(data[asset_id][vs_currency])\n"
                    "\n"
                    "def _fetch_price() -> tuple[float, str]:\n"
                    "    providers = [source]\n"
                    '    if source == "binance":\n'
                    '        providers.append("coingecko")\n'
                    "    else:\n"
                    '        providers.append("binance")\n'
                    "    errors = []\n"
                    "    for provider in providers:\n"
                    "        try:\n"
                    '            if provider == "binance":\n'
                    "                return _fetch_from_binance(), provider\n"
                    "            return _fetch_from_coingecko(), provider\n"
                    "        except Exception as exc:\n"
                    '            errors.append(provider + ":" + str(exc))\n'
                    '    raise RuntimeError("all_sources_failed: " + " | ".join(errors))\n'
                    "\n"
                    "price, resolved_source = _fetch_price()\n"
                    "timestamp = datetime.now(timezone.utc).isoformat()\n"
                    "\n"
                    "if price < lower_bound or price > upper_bound:\n"
                    '    direction = "below" if price < lower_bound else "above"\n'
                    "    print(\n"
                    '        "[ALERT] "\n'
                    "        + asset_id.upper()\n"
                    '        + "/"\n'
                    "        + vs_currency.upper()\n"
                    '        + " is "\n'
                    "        + direction\n"
                    '        + " threshold (price="\n'
                    '        + ("%.4f" % price)\n'
                    '        + ", range="\n'
                    '        + ("%.4f" % lower_bound)\n'
                    '        + "-"\n'
                    '        + ("%.4f" % upper_bound)\n'
                    '        + ", source="\n'
                    "        + resolved_source\n"
                    '        + ", ts="\n'
                    "        + timestamp\n"
                    '        + ")"\n'
                    "    )\n"
                    "else:\n"
                    '    print("[SKIP]")\n'
                ),
                "zh": (
                    "import json\n"
                    "import urllib.request\n"
                    "from datetime import datetime, timezone\n"
                    "\n"
                    'asset_id = "{asset}".strip().lower()\n'
                    'vs_currency = "{quote_currency}".strip().lower()\n'
                    'lower_bound = float("{lower_bound}")\n'
                    'upper_bound = float("{upper_bound}")\n'
                    'source = "{source}".strip().lower()\n'
                    "\n"
                    "def _fetch_from_binance() -> float:\n"
                    "    symbol = asset_id.upper() + vs_currency.upper()\n"
                    '    url = "https://api.binance.com/api/v3/ticker/price?symbol=" + symbol\n'
                    "    with urllib.request.urlopen(url, timeout=12) as resp:\n"
                    '        data = json.loads(resp.read().decode("utf-8"))\n'
                    '    return float(data["price"])\n'
                    "\n"
                    "def _fetch_from_coingecko() -> float:\n"
                    '    url = "https://api.coingecko.com/api/v3/simple/price?ids=" + asset_id + "&vs_currencies=" + vs_currency\n'
                    "    with urllib.request.urlopen(url, timeout=12) as resp:\n"
                    '        data = json.loads(resp.read().decode("utf-8"))\n'
                    "    if asset_id not in data or vs_currency not in data[asset_id]:\n"
                    '        raise RuntimeError("No quote returned for " + asset_id + "/" + vs_currency)\n'
                    "    return float(data[asset_id][vs_currency])\n"
                    "\n"
                    "def _fetch_price() -> tuple[float, str]:\n"
                    "    providers = [source]\n"
                    '    if source == "binance":\n'
                    '        providers.append("coingecko")\n'
                    "    else:\n"
                    '        providers.append("binance")\n'
                    "    errors = []\n"
                    "    for provider in providers:\n"
                    "        try:\n"
                    '            if provider == "binance":\n'
                    "                return _fetch_from_binance(), provider\n"
                    "            return _fetch_from_coingecko(), provider\n"
                    "        except Exception as exc:\n"
                    '            errors.append(provider + ":" + str(exc))\n'
                    '    raise RuntimeError("all_sources_failed: " + " | ".join(errors))\n'
                    "\n"
                    "price, resolved_source = _fetch_price()\n"
                    "timestamp = datetime.now(timezone.utc).isoformat()\n"
                    "\n"
                    "if price < lower_bound or price > upper_bound:\n"
                    '    direction = "below" if price < lower_bound else "above"\n'
                    "    print(\n"
                    '        "[ALERT] "\n'
                    "        + asset_id.upper()\n"
                    '        + "/"\n'
                    "        + vs_currency.upper()\n"
                    '        + " is "\n'
                    "        + direction\n"
                    '        + " threshold (price="\n'
                    '        + ("%.4f" % price)\n'
                    '        + ", range="\n'
                    '        + ("%.4f" % lower_bound)\n'
                    '        + "-"\n'
                    '        + ("%.4f" % upper_bound)\n'
                    '        + ", source="\n'
                    "        + resolved_source\n"
                    '        + ", ts="\n'
                    "        + timestamp\n"
                    '        + ")"\n'
                    "    )\n"
                    "else:\n"
                    '    print("[SKIP]")\n'
                ),
            },
        ),
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="financial_monitor_advanced",
        icon="Eye",
        title={"en": "Financial Monitor (Advanced)", "zh": "金融监控（高级版）"},
        description={
            "en": "Multi-signal financial watch with dedupe, monitor baseline, and failure alerts",
            "zh": "带去重、增量监控与失败告警的多信号金融监控",
        },
        prompt_template={
            "en": (
                "Monitor these assets continuously: {watchlist}. "
                "Evaluate each run with five lenses: price action, derivatives/funding, sentiment (X + news), "
                "macro catalysts, and on-chain flow proxies. "
                "Alert only when at least two independent risk signals align with: {signal_rules}. "
                "Portfolio context: {portfolio_context}. "
                "If there is no actionable change, reply with exactly [SILENT]. "
                "If alerting, return ONLY a minified JSON array sorted by asset symbol. "
                "Each item must contain keys: asset, trigger_reason, confidence, invalidation_level, follow_up_checks. "
                "Do not include timestamps or any prose outside JSON."
            ),
            "zh": (
                "持续监控以下资产：{watchlist}。"
                "每次运行按五个维度评估：价格行为、衍生品/资金费率、情绪（X+新闻）、宏观催化、链上资金流。"
                "仅当至少两个独立风险信号与以下规则同时成立时告警：{signal_rules}。"
                "组合上下文：{portfolio_context}。"
                "若无可执行变化，必须仅回复 [SILENT]。"
                "若触发告警，只输出按资产符号排序的最小化 JSON 数组。"
                "每个元素仅包含键：asset、trigger_reason、confidence、invalidation_level、follow_up_checks。"
                "禁止输出时间戳和 JSON 之外的说明文字。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="09:00"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="weekdays",
                options=("everyday", "weekdays", "weekends"),
            ),
            BlueprintSlot(name="watchlist", type="text", label="watchlist", default="BTC,ETH,SOL"),
            BlueprintSlot(
                name="signal_rules",
                type="text",
                label="signal_rules",
                default="price breakdown + funding flip + sentiment deterioration",
            ),
            BlueprintSlot(
                name="portfolio_context",
                type="text",
                label="portfolio_context",
                default="",
                optional=True,
            ),
        ),
        category="business",
        tags=("finance", "monitoring", "multi-signal", "advanced"),
        sort_order=11,
        default_required_capabilities=_CAP_RESEARCH,
        default_tools_allowed=_TOOLS_RESEARCH,
        job_defaults=BlueprintJobDefaults(
            job_type="agent",
            session_target="daily",
            deduplicate=True,
            skip_if_active=True,
            timeout_seconds=240,
            monitor_config=BlueprintMonitorDefaults(monitor_type="hash", ttl_days=14, enabled=True),
            failure_alert=BlueprintFailureAlertDefaults(enabled=True, after=2, cooldown_seconds=900),
        ),
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="read_it_later",
        icon="BookmarkPlus",
        title={"en": "Read-it-Later Ingestion", "zh": "稍后读知识内化"},
        description={
            "en": "Auto-ingest saved articles into your knowledge base daily",
            "zh": "每天自动将收藏的文章内化到知识库",
        },
        prompt_template={
            "en": (
                "Run the read-it-later ingestion pipeline: "
                "pull unprocessed items from my read-it-later source, "
                "fetch each article's content, ingest into the wiki knowledge base "
                "under Read-it-Later/<current-month>/, and write back a summary "
                "with a 'digested' tag to the source. "
                "Skip items already tagged as processed. Cap at 10 items per run."
            ),
            "zh": (
                "执行稍后读内化流程："
                "从我的稍后读来源拉取未处理的项目，"
                "抓取每篇文章的内容，存入知识库的 Read-it-Later/<当前月份>/ 目录，"
                "并将摘要写回原来源并标记为\u201c已内化\u201d。"
                "跳过已标记的项目。每次最多处理 10 篇。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="06:00"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="everyday",
                options=("everyday", "weekdays", "weekends"),
            ),
        ),
        category="productivity",
        tags=("read-it-later", "knowledge", "ingestion", "wiki", "automation"),
        sort_order=12,
        default_required_capabilities=("net_fetch", "file_read"),
        default_tools_allowed=("web_fetch", "file_read"),
        _schedule_builder="time_weekdays",
    ),
)

BUILTIN_BLUEPRINTS: tuple[CronBlueprint, ...] = tuple(
    _with_supplemental_locales(bp) for bp in _RAW_BUILTIN_BLUEPRINTS
)

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
        raise BlueprintFillError(
            f"unknown slot(s): {', '.join(unknown)} — valid: {', '.join(sorted(known))}"
        )

    effective: dict[str, str] = {}
    for slot in bp.slots:
        raw = values.get(slot.name, slot.default)
        if (
            slot.type == "text"
            and slot.default == ""
            and not str(raw).strip()
            and not slot.optional
        ):
            raise BlueprintFillError(f"missing required value: {slot.name} ({slot.label})")
        if slot.type == "enum" and slot.options and str(raw) not in slot.options:
            raise BlueprintFillError(
                f"{slot.name}={raw!r} not allowed — one of {', '.join(slot.options)}"
            )
        effective[slot.name] = str(raw)
    return effective


def fill_blueprint(
    blueprint_id: str,
    values: dict[str, str],
    *,
    locale: str = "en",
    tz: str | None = None,
) -> BlueprintFillResult | None:
    """Fill a blueprint's slots and produce schedule + prompt.

    Returns None if blueprint_id is unknown.
    Raises BlueprintFillError when slot values are invalid.
    """
    bp = get_blueprint(blueprint_id)
    if not bp:
        return None

    effective_values = _validate_slot_values(bp, values)

    schedule = _build_schedule_from_blueprint(bp, effective_values, tz)
    prompt = _build_prompt_from_blueprint(bp, effective_values, locale)
    pre_condition_script = _build_pre_condition_script(bp, effective_values, locale)
    name = _resolve_locale_title(bp, locale)[:40]
    defaults = bp.job_defaults

    return BlueprintFillResult(
        schedule=schedule,
        prompt=prompt,
        name=name,
        required_capabilities=bp.default_required_capabilities,
        tools_allowed=bp.default_tools_allowed,
        job_type=defaults.job_type,
        session_target=defaults.session_target,
        deduplicate=defaults.deduplicate,
        skip_if_active=defaults.skip_if_active,
        timeout_seconds=defaults.timeout_seconds,
        monitor_config=defaults.monitor_config,
        failure_alert=defaults.failure_alert,
        pre_condition_script=pre_condition_script,
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
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


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
        raise BlueprintFillError(
            "asset must match [a-z0-9-] and start with alphanumeric "
            f"(got {values['asset']!r})"
        )

    quote_currency = values["quote_currency"].strip().lower()
    if not _QUOTE_CURRENCY_RE.fullmatch(quote_currency):
        raise BlueprintFillError(
            "quote_currency must be alphanumeric (2-10 chars), "
            f"got {values['quote_currency']!r}"
        )

    lower = _parse_positive_number(values["lower_bound"], "lower_bound")
    upper = _parse_positive_number(values["upper_bound"], "upper_bound")
    if lower >= upper:
        raise BlueprintFillError(
            f"lower_bound must be less than upper_bound (got {lower:g} >= {upper:g})"
        )

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
    """Generate a concise blueprint catalog for injection into the cron_manage tool description.

    Kept short to avoid bloating the tool schema and harming prompt cache.
    """
    lines: list[str] = ["Available blueprints (use blueprint param for pre-tuned prompts):"]
    for bp in BUILTIN_BLUEPRINTS:
        lang = locale if locale in bp.title else "en"
        title = bp.title.get(lang, bp.title.get("en", bp.id))
        slot_names = ", ".join(_slot_name_for_tool_description(s) for s in bp.slots)
        lines.append(f'  - "{bp.id}": {title} (slots: {slot_names})')
    return "\n".join(lines)
