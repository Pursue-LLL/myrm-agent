"""Search cases for the prebuilt skill library, in the query format the search tool asks an agent for.

[INPUT]
- (none): plain data

[OUTPUT]
- SearchCase: a user intent, the query an agent writes for it, and the skills that satisfy the intent
- AUTHORED_EN / AUTHORED_MIXED: cases written with the skill texts in view (the ceiling, not the typical agent)
- BLIND_EN / BLIND_MIXED: cases written from the user's request alone

[POS]
Data of ``tests/assets/test_prebuilt_skill_search_contract.py``. A query is English keywords (``EN``) or user-language
words plus English keywords (``MIXED``); a case passes when any one of ``expected`` is among the results. The
queries and expected sets were fixed before the first retrieval ran on them: when a case fails, repair retrieval or the
skill description rather than the case.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchCase:
    key: str
    intent: str
    query: str
    expected: frozenset[str]


def _cases(rows: tuple[tuple[str, str, str], ...], expected: dict[str, tuple[str, ...]]) -> tuple[SearchCase, ...]:
    return tuple(SearchCase(key, intent, query, frozenset(expected[key])) for key, intent, query in rows)


_AUTHORED_EXPECTED: dict[str, tuple[str, ...]] = {
    "invoice": ("office-document", "pdf-generator"),
    "minutes": ("meeting-minutes-extractor", "voice-memo-synthesizer"),
    "papers": ("arxiv-research", "deep-research"),
    "tweet": ("x-publish-and-schedule", "x-publish-schedule", "x-publish-schedule-closure", "x-publisher", "xurl"),
    "dbslow": ("db-diagnostics",),
    "video": ("bilibili-content", "youtube-content"),
    "scrape": ("browser-automation", "web-scraping"),
    "review": ("code-review", "code-review-pipeline", "github-workflow"),
    "todo": (
        "daily-briefing",
        "personal-todo-daily-log-weekly-report",
        "personal-todo-daily-weekly-loop",
        "todo-dailylog-weeklyreport-loop",
    ),
    "csv": ("data-analysis", "data-analysis-pipeline"),
    "email": ("google-workspace", "imap-smtp-email"),
    "infographic": ("infographic",),
    "debug": ("systematic-debugging", "test-audit", "test-driven-development"),
    "obsidian": ("obsidian-canvas", "obsidian-notes"),
    "mcp": ("mcp-builder",),
    "seo": ("web-project-seo-optimization",),
    "wechat": ("wechat-article-formatter",),
    "plan": ("multi-agent-orchestration", "task-planning"),
    "ppt": ("office-document", "ppt-outline-quality-gate"),
    "social": ("social-media-monitoring",),
    "finance": ("financial-business-analysis",),
    "organize": ("workspace-auto-organizer",),
    "s2s": (
        "skill-evolution-patcher",
        "task-to-reusable-skill",
        "task-to-skill-flywheel",
        "task-transcript-to-skill",
        "transcript-to-skill-flywheel",
    ),
    "arch": ("architecture-diagram",),
    "react": ("frontend-development", "ui-design"),
}

_AUTHORED_EN_ROWS: tuple[tuple[str, str, str], ...] = (
    ("invoice", "generate a pdf invoice", "pdf invoice/invoice generation/billing document"),
    ("minutes", "turn a meeting recording into minutes", "meeting minutes/meeting notes/action items from recording"),
    ("papers", "find recent academic papers", "research papers/academic papers/literature search"),
    ("tweet", "schedule a tweet", "schedule tweet/post to twitter/social media publishing"),
    ("dbslow", "my postgres database is slow, diagnose it", "postgres slow/database performance/query diagnostics"),
    ("video", "summarize a youtube video", "summarize youtube video/video transcript/video summary"),
    ("scrape", "scrape product prices from a website", "scrape website/web scraping/extract prices crawler"),
    ("review", "review my code", "code review/pull request review/find bugs"),
    ("todo", "write my daily todo and weekly report", "daily plan/weekly report/todo list"),
    ("csv", "analyze a csv file", "csv analysis/data analysis/charts visualization"),
    ("email", "read and send email", "email inbox/imap smtp/mail access"),
    ("infographic", "make an infographic", "infographic/visual summary/chart poster"),
    ("debug", "debug a failing test", "debug failing test/root cause/test debugging"),
    ("obsidian", "create an obsidian mind map canvas", "obsidian mind map/canvas/notes"),
    ("mcp", "build an mcp server", "mcp server/build mcp/model context protocol server"),
    ("seo", "optimize my website for search engines", "seo optimization/search engine optimization/website ranking"),
    (
        "wechat",
        "convert markdown to a wechat official account article",
        "markdown to wechat/wechat official account article/html formatting",
    ),
    ("plan", "break a task down into a plan", "task planning/task breakdown/steps decomposition"),
)

_AUTHORED_MIXED_ROWS: tuple[tuple[str, str, str], ...] = (
    ("minutes", "帮我把会议录音整理成纪要", "会议录音整理成纪要/meeting recording minutes/meeting notes transcript"),
    ("papers", "查一下最新的学术论文", "学术论文/academic papers/arxiv research papers"),
    ("tweet", "定时发推特", "定时发推特/schedule tweet/twitter post scheduling"),
    ("dbslow", "数据库很慢帮我诊断", "数据库诊断/database diagnostics/slow database performance"),
    ("video", "总结一个B站视频", "B站视频总结/bilibili video summary/video transcript"),
    ("scrape", "爬取网页表格数据", "爬取网页表格/web scraping/table extraction"),
    ("review", "代码评审", "代码评审/code review/pull request review"),
    ("todo", "写每日待办和周报", "每日待办周报/daily todo weekly report/task planning journal"),
    ("ppt", "做一份PPT", "做PPT/PowerPoint presentation/slides"),
    ("infographic", "生成信息图", "信息图/infographic/data visualization poster"),
    ("seo", "给我的网站做SEO优化", "网站SEO优化/SEO optimization/search engine optimization website"),
    ("wechat", "把markdown转成公众号文章", "公众号文章/wechat article/markdown to html"),
    ("social", "监控微博和小红书上的品牌提及", "社交媒体监控/social media monitoring/brand mention weibo xiaohongshu"),
    ("finance", "分析财报", "财报分析/financial statement analysis/financial filings 10-K"),
    ("debug", "调试一个反复失败的bug", "调试bug/debugging/root cause failing bug"),
    ("plan", "拆解任务做计划", "任务拆解计划/task planning/task decomposition"),
    ("organize", "整理工作目录文件", "整理文件目录/organize files folder/workspace file classification"),
    ("s2s", "把这次对话沉淀成可复用技能", "对话沉淀成技能/conversation to reusable skill/transcript to skill"),
    ("email", "发送邮件", "发送邮件/send email/smtp mail"),
    ("arch", "做一个架构图", "架构图/architecture diagram/system design diagram"),
    ("react", "写一个react组件", "react组件/react component/frontend development"),
)

_BLIND_EXPECTED: dict[str, tuple[str, ...]] = {
    "ast": ("ast-grep-search", "ast-grep-structural-search"),
    "blender": ("blender-mcp",),
    "readlater": ("read-it-later",),
    "secscan": ("security-diff-scan", "security-fix-finding"),
    "matherr": ("math-error-book",),
    "hostops": ("host-server-ops",),
    "webdesign": ("popular-web-designs",),
    "humanize": ("content-humanizer",),
    "study": ("academic-subject-study",),
    "brainstorm": ("creative-ideation",),
    "docextract": ("document-extraction",),
    "xsearch": ("x-live-search", "xurl"),
    "ghinstall": ("github-skill-dynamic-installer", "github-skill-installer-auditor"),
    "mcpexp": ("mcp-expiry-watchdog", "mcp-proactive-reauth-watchdog", "mcp-reauth-watchdog"),
    "competitor": ("competitive-analysis-pipeline",),
    "erp": ("legacy-erp-automation",),
    "voice": ("persona-voice",),
}

_BLIND_EN_ROWS: tuple[tuple[str, str, str], ...] = (
    (
        "ast",
        "find all places where this API is called regardless of formatting and change them all",
        "structural code search refactor",
    ),
    ("blender", "make a low poly spaceship in Blender", "Blender 3D model render"),
    ("readlater", "pull in the articles I saved in Pocket and summarize them", "read later saved articles knowledge base"),
    ("secscan", "is my pull request safe, any vulnerabilities in the diff", "security vulnerability scan code fix"),
    ("matherr", "I keep making the same mistakes in calculus problems, track them for me", "math mistakes notebook review"),
    ("hostops", "my server feels slow, check what is wrong", "server health check cpu memory disk"),
    ("webdesign", "make my landing page look like Stripe's", "web page design style Stripe Vercel"),
    ("humanize", "this reads like ChatGPT wrote it, make it less robotic", "humanize AI text human-like writing"),
    ("study", "I am struggling with quantum mechanics, help me actually understand it", "study physics subject learning plan"),
    ("brainstorm", "I need fresh ideas for a side project", "brainstorm ideas new product"),
    ("docextract", "get the tables out of this scanned report", "extract tables PDF multi-page"),
    ("xsearch", "what are people saying on Twitter about this launch", "search X Twitter posts topic"),
    ("ghinstall", "I found a skill on GitHub, can you install it for me", "install skill GitHub repo community"),
    ("mcpexp", "my MCP login keeps expiring, remind me before it does", "MCP credentials expire reminder"),
    ("competitor", "how do we stack up against our rivals", "compare competitors analysis"),
    ("erp", "I need to enter data into our ancient desktop ERP, there is no API", "automate legacy ERP Windows app"),
    ("voice", "make the assistant write the way I write", "learn writing style from samples"),
)

_BLIND_MIXED_ROWS: tuple[tuple[str, str, str], ...] = (
    ("ast", "找出所有调用这个接口的地方，不管代码怎么排版，然后统一改掉", "代码结构搜索/structural code search refactor"),
    ("blender", "用 Blender 做一个低多边形飞船", "Blender 建模/Blender 3D model render"),
    ("readlater", "把我在 Pocket 里存的文章拉下来总结一下", "稍后阅读/read later saved articles knowledge base"),
    ("secscan", "我这个 PR 安全吗？改动里有没有漏洞", "安全漏洞/security vulnerability scan code fix"),
    ("matherr", "微积分题老是犯同样的错，帮我记下来复习", "错题本/math mistakes notebook review"),
    ("hostops", "服务器变慢了，帮我查查怎么回事", "服务器检查/server health check cpu memory disk"),
    ("webdesign", "让我的落地页看起来像 Stripe 那样", "网页设计风格/web page design style Stripe Vercel"),
    ("humanize", "这段话一看就是 AI 写的，帮我改得自然点", "去AI味/humanize AI text human-like writing"),
    ("study", "量子力学我老是学不懂，帮我真正搞明白", "学科学习/study physics subject learning plan"),
    ("brainstorm", "我想给副业项目找点新点子", "头脑风暴/brainstorm ideas new product"),
    ("docextract", "把这份报告里的表格弄出来", "PDF 表格提取/extract tables PDF multi-page"),
    ("xsearch", "推特上大家怎么评价这次发布", "X 搜索/search X Twitter posts topic"),
    ("ghinstall", "我在 GitHub 上看到一个技能，帮我装上", "安装技能/install skill GitHub repo community"),
    ("mcpexp", "MCP 登录老是过期，过期之前提醒我", "MCP 授权过期/MCP credentials expire reminder"),
    ("competitor", "我们和对手比起来怎么样", "竞品对比/compare competitors analysis"),
    ("erp", "我要往公司那套老桌面 ERP 里录数据，没有接口", "老 ERP 自动化/automate legacy ERP Windows app"),
    ("voice", "让助手用我平时的语气写东西", "文风学习/learn writing style from samples"),
)

AUTHORED_EN = _cases(_AUTHORED_EN_ROWS, _AUTHORED_EXPECTED)
AUTHORED_MIXED = _cases(_AUTHORED_MIXED_ROWS, _AUTHORED_EXPECTED)
BLIND_EN = _cases(_BLIND_EN_ROWS, _BLIND_EXPECTED)
BLIND_MIXED = _cases(_BLIND_MIXED_ROWS, _BLIND_EXPECTED)
