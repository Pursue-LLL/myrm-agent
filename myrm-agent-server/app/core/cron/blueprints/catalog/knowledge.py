"""知识库蓝图：稍后读内化、wiki 晨间增量、维护、vault 周检、日报复利、语料去重。

[POS]
Cron 蓝图目录的一部分；由 app/core/cron/blueprints.py 按声明顺序拼成内置清单。
"""

from app.core.cron.blueprints.core.types import (
    _CAP_WIKI,
    _TOOLS_WIKI,
    BlueprintJobDefaults,
    BlueprintSlot,
    CronBlueprint,
)

BLUEPRINTS: tuple[CronBlueprint, ...] = (
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
                "Wiki source sync job (router mode). The sync summary is produced by the server; "
                "deliver it as-is. Reply [SILENT] when nothing was ingested."
            ),
            "zh": ("知识库来源同步任务（router 模式）。同步摘要由服务端生成，请原样投递。若无新内容则回复 [SILENT]。"),
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
        default_required_capabilities=(),
        default_tools_allowed=(),
        job_defaults=BlueprintJobDefaults(
            job_type="router",
            session_target="isolated",
            deduplicate=True,
            skip_if_active=True,
            timeout_seconds=120,
            command="__wiki_source_sync__",
        ),
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="wiki_morning_delta",
        icon="BookMarked",
        title={"en": "Wiki Morning Delta", "zh": "知识库晨间摘要"},
        description={
            "en": "Daily vault delta digest: organize new raw notes and summarize changes",
            "zh": "每日检查知识库变更，整理新 raw 笔记并输出简短摘要",
        },
        prompt_template={
            "en": (
                "Run the wiki morning delta routine for the last 24 hours:\n"
                "1. Scan raw/ for new or updated source files that still need organizing.\n"
                "2. Use wiki_query_tool to inspect related concepts; use wiki_apply_tool only "
                "for small metadata or timeline updates when clearly needed.\n"
                "3. Note outdated wiki pages that may need attention (do not rewrite whole articles).\n"
                "4. Reply with at most 3 short lines summarizing what changed in the vault "
                "(new ingests, compiles, edits, or maintenance findings).\n"
                "If nothing meaningful changed, reply with exactly [SILENT]."
            ),
            "zh": (
                "执行过去 24 小时的知识库晨间巡检：\n"
                "1. 扫描 raw/ 中新增或更新、仍需整理的原始文件。\n"
                "2. 用 wiki_query_tool 查看相关概念；仅在必要时用 wiki_apply_tool 做少量元数据或时间线条目更新。\n"
                "3. 标记可能过时的 wiki 页面（不要整页重写）。\n"
                "4. 用不超过 3 行简短总结 vault 发生了什么变化（新入库、编译、编辑或维护发现）。\n"
                "若无实质变化，必须仅回复 [SILENT]。"
            ),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="07:00"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="everyday",
                options=("everyday", "weekdays", "weekends"),
            ),
        ),
        category="productivity",
        tags=("wiki", "digest", "daily", "second-brain", "knowledge"),
        sort_order=13,
        default_required_capabilities=_CAP_WIKI,
        default_tools_allowed=_TOOLS_WIKI,
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="wiki_maintain",
        icon="Wrench",
        title={"en": "Wiki Vault Maintenance", "zh": "知识库自动维护"},
        description={
            "en": "Scheduled structural lint and auto-repair for broken links, stale raw, and vault hygiene",
            "zh": "定时执行知识库结构巡检，自动修复断链、过期 raw 与安全项",
        },
        prompt_template={
            "en": (
                "Wiki maintain job (router mode). The maintenance summary is produced by the server; "
                "deliver it as-is. Reply [SILENT] when nothing changed."
            ),
            "zh": ("知识库维护任务（router 模式）。维护摘要由服务端生成，请原样投递。若无变化则回复 [SILENT]。"),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="03:00"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="weekends",
                options=("everyday", "weekdays", "weekends"),
            ),
            BlueprintSlot(
                name="mode",
                type="enum",
                label="mode",
                default="structural",
                options=("structural", "full"),
            ),
        ),
        category="productivity",
        tags=("wiki", "maintenance", "lint", "automation", "second-brain"),
        sort_order=14,
        default_required_capabilities=(),
        default_tools_allowed=(),
        job_defaults=BlueprintJobDefaults(
            job_type="router",
            session_target="isolated",
            deduplicate=True,
            skip_if_active=True,
            timeout_seconds=900,
            command="__wiki_maintain__:structural",
        ),
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="wiki_vault_weekly_health",
        icon="Activity",
        title={"en": "Wiki Vault Weekly Health (List Only)", "zh": "知识库每周健康巡检（只列不修）"},
        description={
            "en": "Weekly zero-fix health check list for broken links, stale sources, and orphan notes",
            "zh": "每周日定时只读巡检知识库，生成断链/过期事实/草稿体检清单，绝不擅自修改任何文件",
        },
        prompt_template={
            "en": (
                "Wiki vault health check job (router mode, list-only). The markdown health list is produced by the server; "
                "deliver it directly to the user."
            ),
            "zh": ("知识库健康周检任务（router 模式，只列不修）。体检清单由服务端生成，请直接投递给用户。"),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="18:00"),
            BlueprintSlot(
                name="day",
                type="enum",
                label="weekday",
                default="0",
                options=("0", "1", "2", "3", "4", "5", "6"),
            ),
        ),
        category="productivity",
        tags=("wiki", "health", "doctor", "list-only", "automation", "second-brain"),
        sort_order=15,
        default_required_capabilities=(),
        default_tools_allowed=(),
        job_defaults=BlueprintJobDefaults(
            job_type="router",
            session_target="isolated",
            deduplicate=True,
            skip_if_active=True,
            timeout_seconds=600,
            command="__wiki_maintain__:list_only",
        ),
        _schedule_builder="time_weekday",
    ),
    CronBlueprint(
        id="daily_review_compounding",
        icon="NotebookPen",
        title={"en": "Daily Review Compounding", "zh": "每日复盘知识化"},
        description={
            "en": "Compile today's daily-review journals into four-dimension knowledge drafts awaiting review",
            "zh": "晚间汇总当日复盘日志，自动萃取为项目/知识/方法/对比四维知识草稿，等待人工审核",
        },
        prompt_template={
            "en": (
                "Daily review compounding job (router mode). The compounding summary is produced "
                "by the server; deliver it as-is. Reply [SILENT] when nothing was ingested."
            ),
            "zh": ("每日复盘知识化任务（router 模式）。汇总摘要由服务端生成，请原样投递。若无复盘输入则回复 [SILENT]。"),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="21:30"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="everyday",
                options=("everyday", "weekdays", "weekends"),
            ),
        ),
        category="productivity",
        tags=("wiki", "daily-review", "knowledge", "compounding", "second-brain", "automation"),
        sort_order=16,
        default_required_capabilities=(),
        default_tools_allowed=(),
        job_defaults=BlueprintJobDefaults(
            job_type="router",
            session_target="isolated",
            deduplicate=True,
            skip_if_active=True,
            timeout_seconds=300,
            command="__wiki_daily_review_compound__",
        ),
        _schedule_builder="time_weekdays",
    ),
    CronBlueprint(
        id="wiki_corpus_dedup",
        icon="Copy",
        title={"en": "Wiki Corpus Dedup Scan", "zh": "知识库语料去重扫描"},
        description={
            "en": "Scheduled scan for exact, normalized, and near-duplicate raw sources with review queue",
            "zh": "定时扫描 raw 语料的精确/归一化/近似重复，并写入待审核队列",
        },
        prompt_template={
            "en": (
                "Wiki corpus dedup job (router mode). The dedup summary is produced by the server; "
                "deliver it as-is. Reply [SILENT] when no duplicate groups need review."
            ),
            "zh": ("知识库语料去重任务（router 模式）。去重摘要由服务端生成，请原样投递。若无待审核重复组则回复 [SILENT]。"),
        },
        slots=(
            BlueprintSlot(name="time", type="time", label="time", default="04:30"),
            BlueprintSlot(
                name="weekdays",
                type="enum",
                label="weekdays",
                default="weekends",
                options=("everyday", "weekdays", "weekends"),
            ),
        ),
        category="productivity",
        tags=("wiki", "dedup", "hygiene", "automation", "second-brain"),
        sort_order=17,
        default_required_capabilities=(),
        default_tools_allowed=(),
        job_defaults=BlueprintJobDefaults(
            job_type="router",
            session_target="isolated",
            deduplicate=True,
            skip_if_active=True,
            timeout_seconds=600,
            command="__wiki_dedup__",
        ),
        _schedule_builder="time_weekdays",
    ),
)
