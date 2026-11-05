"""增长蓝图：病毒式引语发现。

[POS]
Cron 蓝图目录的一部分；由 app/core/cron/blueprints.py 按声明顺序拼成内置清单。
"""

from app.core.cron.blueprints_types import (
    _CAP_RESEARCH,
    _CAP_RESEARCH_SAVE,
    _TOOLS_RESEARCH,
    BlueprintSlot,
    CronBlueprint,
)

BLUEPRINTS: tuple[CronBlueprint, ...] = (
    CronBlueprint(
        id="seo_weekly_audit",
        icon="Search",
        title={"en": "SEO & Site Health Weekly Audit", "zh": "SEO 与网站健康周度巡检"},
        description={
            "en": "Scheduled audit of technical SEO, robots, sitemap, meta tags, and AI search readiness with prioritized roadmap",
            "zh": "定时巡检网站 technical SEO、robots、sitemap、标签与 AI 搜索就绪度，生成优先级路线图",
        },
        prompt_template={
            "en": (
                "Run a comprehensive technical SEO and site health audit for {target_url} (depth: {depth}).\n"
                "1. Fetch and verify robots.txt, sitemap.xml, and /llms.txt if present.\n"
                "2. Inspect core rendered pages for title, meta description, canonical, H1, JSON-LD, OpenGraph, and hreflang.\n"
                "3. Check for dead internal links and broken images.\n"
                "4. Generate a prioritized P0-P3 SEO-OPTIMIZATION-ROADMAP.md artifact in artifacts/ with concrete evidence.\n"
                "5. Provide a crisp executive summary of critical issues and actionable next steps."
            ),
            "zh": (
                "对目标站点 {target_url} 执行全面的技术 SEO 与站点健康巡检（检测深度: {depth}）。\n"
                "1. 抓取并验证 robots.txt、sitemap.xml 以及 /llms.txt（若存在）。\n"
                "2. 深度检查核心页面的 title、meta description、canonical、H1、JSON-LD 结构化数据、OpenGraph 及 hreflang。\n"
                "3. 采样检测站内死链与缺失 alt 的图片。\n"
                "4. 在 artifacts/ 目录生成带真实证据的 P0-P3 结构化 SEO-OPTIMIZATION-ROADMAP.md 工件。\n"
                "5. 输出精炼的高管摘要，列出致命缺陷与本周可执行的优化动作。"
            ),
        },
        slots=(
            BlueprintSlot(
                name="target_url",
                type="text",
                label="target_url",
                default="https://example.com",
            ),
            BlueprintSlot(
                name="depth",
                type="enum",
                label="depth",
                default="standard",
                options=("quick", "standard", "deep"),
            ),
            BlueprintSlot(name="time", type="time", label="time", default="09:00"),
            BlueprintSlot(
                name="day",
                type="enum",
                label="day",
                default="1",
                options=("1", "2", "3", "4", "5", "6", "0"),
            ),
        ),
        category="marketing-growth",
        tags=("seo", "audit", "marketing", "website", "weekly"),
        sort_order=18,
        default_required_capabilities=_CAP_RESEARCH_SAVE,
        default_tools_allowed=_TOOLS_RESEARCH,
        _schedule_builder="time_weekday",
    ),
    CronBlueprint(
        id="viral_quote_discovery",
        icon="Flame",
        title={"en": "Viral Quote & Hook Discovery", "zh": "高潜爆款金句与选题提炼"},
        description={
            "en": "Daily surveillance of social networks and industry blogs to mine viral hooks, contrasting arguments, and quotes",
            "zh": "定时巡检社媒网络与行业前沿，挖掘高传播金句、反共识论点与金牌选题",
        },
        prompt_template={
            "en": (
                "Execute viral quote and golden hook discovery for topic: {topic} across target channels: {channels}.\n"
                "1. Search recent popular discussions (last 24-48 hours) for high-engagement posts.\n"
                "2. Extract top 5 viral quote candidates featuring counter-intuitive insights or strong emotional resonance.\n"
                "3. Deconstruct why each quote works (Hook formula, pain point addressed, audience reaction).\n"
                "4. Synthesize adapted derivative ideas for X threads, Xiaohongshu notes, and WeChat newsletters.\n"
                "5. Save the curated quotes into `docs/marketing/viral_quotes_{topic}.md` and summarize the top candidate."
            ),
            "zh": (
                "执行关于主题【{topic}】的高潜爆款金句与选题提炼，覆盖渠道：{channels}。\n"
                "1. 检索过去 24-48 小时内的全网热门讨论与高互动内容。\n"
                "2. 提炼 Top 5 具备反共识视角、高传播力或强烈共鸣的金句候选。\n"
                "3. 深度拆解爆款密码（钩子公式、击中的用户痛点、争议点与情绪价值）。\n"
                "4. 为 X 串推、小红书图文和微信长文分别衍生对应的二创选题建议。\n"
                "5. 将金句库归档至 `docs/marketing/viral_quotes_{topic}.md` 并精简输出最优主推金句。"
            ),
        },
        slots=(
            BlueprintSlot(
                name="topic",
                type="text",
                label="topic",
                default="AI Agent & Vibe Coding",
            ),
            BlueprintSlot(
                name="channels",
                type="text",
                label="channels",
                default="X (Twitter), Xiaohongshu, HackerNews",
            ),
            BlueprintSlot(name="time", type="time", label="time", default="08:30"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="everyday",
                options=("everyday", "weekdays", "weekends"),
            ),
        ),
        category="marketing-growth",
        tags=("marketing", "viral", "quote", "social-media", "content"),
        sort_order=19,
        default_required_capabilities=_CAP_RESEARCH_SAVE,
        default_tools_allowed=_TOOLS_RESEARCH,
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="commerce_morning_digest",
        icon="Store",
        title={"en": "Daily Commerce Morning Digest", "zh": "店铺经营晨报与全盘诊断"},
        description={
            "en": "Automated headless morning briefing analyzing GMV, conversion rates, stockout risks, and staged promotions",
            "zh": "自动化商业晨报诊断，深度分析销售大盘、缺货告警、两阶段调价提案与库存建议",
        },
        prompt_template={
            "en": (
                "Produce the morning commerce digest for store '{store_name}': review yesterday's GMV, "
                "order volume, conversion rate, and inventory health. Highlight any critical low-stock items "
                "or pending staged changes that require operator sign-off, and provide prioritized action recommendations."
            ),
            "zh": (
                "为店铺「{store_name}」生成今日经营晨报与全盘诊断：汇总分析销售额(GMV)、订单量、转化率波动与库存健康度。"
                "重点标出严重缺货预警与待审批的暂存调价变更，并给出优先级操作处置建议。"
            ),
        },
        slots=(
            BlueprintSlot(name="store_name", type="text", label="store_name", default="Flagship Store"),
            BlueprintSlot(name="time", type="time", label="time", default="08:30"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="everyday",
                options=("everyday", "weekdays", "weekends"),
            ),
        ),
        category="commerce",
        tags=("commerce", "merchant", "digest", "kpi"),
        sort_order=20,
        default_required_capabilities=_CAP_RESEARCH,
        default_tools_allowed=_TOOLS_RESEARCH,
        _schedule_builder="time_weekdays",
    ),
)
