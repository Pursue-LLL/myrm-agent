# daily_review/

## 架构概述

每日复盘日志驱动的四维知识自动进化域：复盘原文 verbatim 存证 → 四维分流编译 → HITL 待审发布。
四维体系 = Projects / Knowledge / Methods / Comparisons。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 域 facade 导出 | ✅ |
| `ingest.py` | SSOT | `ingest_daily_review_text`：复盘原文 verbatim 存证 `raw/DailyReview/YYYY-MM-DD_<slug>.md`（同日同题幂等 skip、安全扫描 422）+ 编译入队；`DAILY_REVIEW_RAW_DIR` 目录 SSOT | ✅ |
| `prompts.py` | SSOT | `FOUR_DIMENSION_EXTRACT_PROMPT`：vault 全局四维分流概念提取提示词（经 `WikiCompileConfig.extract_concepts_prompt_template` 扩展点注入 archiver 共享 compiler，harness 零改动） | ✅ |
| `runner.py` | SSOT | `run_wiki_daily_review_compound_job`（cron `__wiki_daily_review_compound__`）：24h 窗口复盘汇总（mtime 相对窗口，覆盖晚间/凌晨写入者，不受日历日/时区影响）+ 停滞队列兜底 `compile_all`（跟随窗口）+ 窗口四维草稿分布统计（status 无关：已审草稿不消失；同概念去重防重编译双计；`get_stats` 准确总数不受 LIMIT 50 截断）；窗口无复盘输入回复 `[SILENT]`；英文汇总（对齐 dedup_runner 约定）+ `?wikiTab=pendingEdits` 深链 | ✅ |
| `schemas.py` | 契约 | `DailyReviewIngestResult` / `WikiDailyReviewCompoundResult` DTO | ✅ |
| `templates.py` | SSOT | 四张标准双语模板（Daily Review / Project / Knowledge Note / Method）幂等种子 `concepts/templates/`；marker 文件防启动复活用户删除的模板；`force` 显式覆盖 | ✅ |

## 模块依赖

- `app.services.wiki.source_sync.publish_helpers` — raw frontmatter + 路径段清洗
- `myrm_agent_harness.toolkits.wiki.pipeline.raw_gate` — verbatim raw 发布门禁
- `app.services.wiki.vault` — archiver 进程缓存单例 + vault 路径 SSOT
- `app.api.wiki.router` — `POST /wiki/daily-review`、`POST /wiki/templates/seed` REST 端点 + 变异钩子（缓存失效 + git 快照）
- `app.core.cron.adapters.wiki_router_job_runner` — cron 命令派发
