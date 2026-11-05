"""日常节奏蓝图：晨报、周复盘、提醒、资讯、晚间收尾、健康检查、竞品与习惯、学习、社媒观察。

[POS]
Cron 蓝图目录的一部分；由 app/core/cron/blueprints.py 按声明顺序拼成内置清单。
"""

from app.core.cron.blueprints_types import (
    _CAP_DEVOPS,
    _CAP_RESEARCH,
    _CAP_WEB,
    _TOOLS_DEVOPS,
    _TOOLS_RESEARCH,
    _TOOLS_WEB,
    BlueprintSlot,
    CronBlueprint,
)

BLUEPRINTS: tuple[CronBlueprint, ...] = (
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
            "zh": ("提供一份简洁的早间简报，涵盖：重要新闻头条、天气预报、以及今天的重要提醒事项。保持简短且可操作。"),
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
            "zh": ("进行一次全面的每周回顾：总结本周关键成果、识别遇到的阻碍或挑战，并建议下周的优先事项。按类别组织。"),
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
            "zh": ("提供一份平和的晚间总结：简要回顾今天的亮点、预览明天的日程和优先事项，并提供一条放松建议或晚间灵感语录。"),
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
                "Execute the host-server-ops health inspection workflow. Check CPU load, "
                "memory utilization, remaining disk headroom, and critical daemon/service status. "
                "Produce a structured health brief with status level (OK / WARN / CRIT) and triage advice."
            ),
            "zh": (
                "执行 host-server-ops 主机健康巡检工作流。检查 CPU 负载、"
                "内存利用率、剩余磁盘空间以及关键守护进程/服务运行状态。"
                "生成包含状态评级（OK / WARN / CRIT）及排障处置建议的结构化健康简报。"
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
        default_skill_ids=("host-server-ops",),
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
)
