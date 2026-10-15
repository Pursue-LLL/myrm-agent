# maintain/

Wiki maintain 域子包 — 编排、schemas 与状态持久化。

## 架构概述

聚合 wiki maintain 管线：REST /maintain 与 Cron `__wiki_maintain__` 共用执行体（`runner`）、运行登记与单飞（`run_registry`）、DTO（`schemas`）、UserConfig 上次维护状态持久化（`state_store`）。模块名 `app.services.wiki.maintain`。

全量维护最多 25 次串行模型调用（数分钟），超过云端代理等待响应的时间，所以 REST 只负责启动后台运行并返回状态，前端轮询 `GET /maintain/status`。用户可以随时取消（`POST /maintain/cancel`，幂等，返回当前状态）：登记里的 `stop` 事件交给 harness，运行在模型调用之间停下，已写入的修复与链接保留，状态为 `cancelled`，之后照常收尾（索引、健康快照、状态持久化）；只有模型阶段可以取消，结构性维护几乎瞬间完成。同一知识库范围同一时刻只允许一轮（REST 与 Cron 共用同一登记）；运行登记在内存里，因为它是本进程的瞬时进度，运行结果另由 `state_store` 与 vault 健康快照持久化。服务端以单进程运行（`run.py` 默认 uvicorn 单进程；多进程的 granian 只适用于没有嵌入式数据库的部署），所以登记不需要跨进程共享；重启后进行中的一轮随进程消失，状态回到 `idle`。

上级文档：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出 runner/run_registry/schemas/state_store 公开符号 | ✅ |
| `runner.py` | SSOT | 维护管线（`_list_issues` 只读列表 / `_lint_and_maintain` 修复与健康快照，共用 `_save_state` 与 `_persist_health_snapshot`）与两个入口：`schedule_wiki_maintain`（REST，后台运行，已有进行中的一轮则返回它；compile 进行中返回 `compile_in_progress`）、`run_wiki_maintain_job`（Cron，阻塞到结束；已有一轮在跑则静默跳过 `maintain_in_progress`，不写状态；`list_only` 只读不占单飞）；单轮 45 分钟硬上限（提供商卡死时释放知识库）；失败只对外暴露错误码；`stop` 事件经 `lint_and_maintain(stop=)` 传给 harness，停下的一轮 `cancelled=true` 且 cron 摘要恒为 `[SILENT]`；模型一次也没应答（未配置提供商、Key 失效、提供商不可用）时结果带 `ai_unavailable`，结构性修复照常完成，cron 摘要不再静默；返回最多 200 条 lint issues + vault `reports/last-health.json` 快照 | ✅ |
| `reporting.py` | 核心 | 运行结果对外的文本与载荷（纯函数）：`lint_issue_payloads`（最多 200 条）、`build_summary_text`（cron 摘要，无变化且模型正常、或被用户取消时 `[SILENT]`）、`build_list_only_report`（`list_only` 周检 Markdown 报告） | ✅ |
| `run_registry.py` | 核心 | 每个知识库范围最近一轮的实时状态（阶段、done/total、`stop` 事件、结果、错误码）与单飞：检查与占位之间没有 `await`，不需要锁；`cancel_requested`（进行中且已请求取消，状态接口据此让重载后的页面仍显示「正在停止」）；`cancel_wiki_maintain` 只对进行中的一轮置位 `stop`，结束的一轮原样返回；结束的一轮保留到下一轮替换 | ✅ |
| `schemas.py` | 类型 | `WikiMaintainState` / `WikiMaintainRunResult`（含 `ai_unavailable`、`cancelled`）/ `WikiMaintainModeLiteral` | ✅ |
| `stale_archiver.py` | 核心 | `StaleFileArchiver` — 探测与归档过期草稿与失效 deprecated 文档 | ✅ |
| `state_store.py` | 持久化 | UserConfig `wikiMaintainState` 上次维护 observability（按 agent） | ✅ |

## 依赖

- `app/services/wiki/_userconfig_scoped` — 共享 UserConfig scoped JSON 持久化（state_store 复用）
- `app.services.wiki.vault` — archiver / compile enqueue / health report
- `app.services.wiki.health_report_service` — `count_open_actions` (POS: vault health snapshot)
- `app.core.cron` — `__wiki_maintain__` router job
- `myrm_agent_harness.toolkits.wiki.maintenance.progress` — 运行阶段进度观察者（登记只存最新一条，不进模型提示）
- `myrm_agent_harness.toolkits.wiki.core.types` — `LintIssue`（运行结果里的 issue 载荷）
