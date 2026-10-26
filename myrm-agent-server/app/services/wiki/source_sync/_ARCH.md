# source_sync/

## 架构概述

Wiki 外部来源确定性同步：Feishu 文档 / Gmail 标签 / Google Drive 文件夹 / RSS / Zotero 文献库 / Integration mirror → harness `publish_raw` → 可选 compile enqueue（经 `deferred_enqueue` 推迟到去重扫描之后，重复文档不会被编译两次）。零 LLM pull；Cron 经 `__wiki_source_sync__` router job 触发。配置与 sync state 按 agent scope 存 UserConfig。

上级文档：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包级文档；消费者直接 import runner / schemas / config_store / state_store | — |
| `schemas.py` | 类型 | `WikiSourceSyncConfig`（Feishu/Gmail/GDrive/RSS/Zotero/mirror）/ state / run summary DTO | ✅ |
| `config_store.py` | 持久化 | UserConfig `wikiSourceSync` 按 agent 读写 + exists 探测 | ✅ |
| `state_store.py` | 持久化 | UserConfig `wikiSourceSyncState` 上次同步状态（按 agent） | ✅ |
| `content_convert.py` | 辅助 | 云盘文件 bytes → Markdown（sniff+docx embed→wiki/assets） | ✅ |
| `publish_helpers.py` | 辅助 | 统一 `publish_raw(caller=settings)` + frontmatter；`publish_source_markdown` 支持 `conflict_policy`（默认 SKIP，ima 用 SUPERSEDE）；`sanitize_path_segment` 同时受字符与字节预算约束 | ✅ |
| `feishu/` | 连接器 | Feishu 域 — 门面 + 纯函数渲染；见 [`feishu/_ARCH.md`](feishu/_ARCH.md) | ✅ |
| `gmail/` | 连接器 | Gmail 域 — 门面 + HTML 渲染；见 [`gmail/_ARCH.md`](gmail/_ARCH.md) | ✅ |
| `gdrive.py` | 连接器 | Google OAuth + Drive API → raw/gdrive/ | ✅ |
| `rss.py` | 连接器 | RSS/Atom HTTP → raw/rss/ | ✅ |
| `zotero.py` | 连接器 | Zotero Web API v3 文献库 → raw/zotero/<月份>/<item key>.md（top-level items 最新修改优先 + 子项高亮/注释标注 best-effort；`_is_allowed_base_url` 校验 scheme+netloc 防 SSRF） | ✅ |
| `integration_mirror.py` | 钩子 | IntegrationSyncResult.new_items → raw/integrations/（入队器由 `runner` 注入） | ✅ |
| `read_it_later_hygiene.py` | 迁移 | 存量 agent-type read-it-later Cron → router `__wiki_source_sync__` | ✅ |
| `ima/` | 连接器 | 腾讯 ima 知识库与笔记只读导入 — 台账 + 时间盒 cron 切片 + 断点续跑；见 [`ima/_ARCH.md`](ima/_ARCH.md) | ✅ |
| `defaults.py` | 默认 | Google OAuth / Second Brain apply 默认开 Gmail read-later | ✅ |
| `deferred_enqueue.py` | 编排 | `DeferredCompileEnqueue`：与 `compiler.enqueue_file` 同形的入队替身，发布时只登记路径；`release(scan_completed=…)` 在 dedup 扫描**完成**后把未被 open EXACT/NORMALIZED 重复组占用的文件交给 compiler（组成员留给用户在 Duplicate Review 处理，处理后手动编译——Wiki 的「编译」经 `enqueue_changed_sources`、ima 卡片的「编译」经 `compile_imported`——再选入）；扫描被跳过/失败时不信任已存的旧分组、全部放行，去重库不可读时同样全部放行，不丢文档 | ✅ |
| `runner.py` | 编排 | `run_wiki_source_sync` SSOT（Feishu/Gmail/GDrive/RSS/Zotero/mirror pull → `run_post_sync_dedup_scan` when published > 0 → `finally` 内 `release(scan_completed=…)` 延迟入队 → ingest 快照 → scoped state）；连接器只收到 `DeferredCompileEnqueue`，入口处才决定放行 | ✅ |

## 测试

- `tests/services/wiki/test_source_sync_{gmail,gmail_html,gdrive,rss,state,config,defaults,blueprint}.py`
- `tests/services/wiki/test_feishu_source_sync.py` — Feishu Docx blocks 全量渲染（标题/列表/嵌套列表缩进+独立计数/代码+围栏自适应/引用/待办/文件块/图片/行内样式+链接+URL解码/议程块/通用降级/@用户/@文档/日期提醒/公式/`$`转义）
- `tests/services/wiki/test_feishu_images.py` — 图片下载→wiki/assets 落盘 + 失败降级
- `tests/services/wiki/test_zotero_source_sync.py` — Zotero 连接器单测（creators 格式化/文献笔记渲染/标注渲染/config 缺失 fail-fast/base_url 校验/发布计数/拉取失败计账）
- `tests/api/wiki/test_wiki_sources_status.py` — sources API：status 标志位 + PUT config zotero 字段透传/回读断言 + exclude_unset 部分更新保持语义（断链防回归锚点）
- `tests/services/wiki/source_sync/test_publish_helpers.py` — 冲突策略透传 + 路径段字节预算
- `tests/services/wiki/source_sync/test_deferred_enqueue.py` — 延迟入队：放行前不入 compile 队列；EXACT/NORMALIZED 组成员被留住、NEAR 不留；组被处理后放行；未完成扫描时连已存分组的成员也放行；去重库不可读/单个入队失败都不丢文档
- `tests/services/wiki/source_sync/test_runner_deferred_compile.py` — 一次 source-sync 运行：重复文档不被编译两次且顺序为 扫描 → 放行 → 快照；连接器中途崩溃、扫描失败与扫描被跳过仍放行；关闭自动编译时不延迟；integration mirror 使用被注入的入队器
- `tests/services/wiki/source_sync/ima/` — 见 [`ima/_ARCH.md`](ima/_ARCH.md)
- `tests/services/wiki/test_read_it_later_hygiene.py`
- `tests/services/onboarding/test_second_brain_wiki_gmail.py`

## 依赖

- `app/services/wiki/_userconfig_scoped` — 共享 UserConfig scoped JSON 持久化（config/state store 复用）
- `app/services/integrations/oauth_store` — Google 连接探测
- `app/services/agent/oauth_refresher` — Gmail / Drive token
- `app/services/wiki/vault` — archiver / compile enqueue
- `app/services/wiki/dedup_runner` — `run_post_sync_dedup_scan`（post-sync 增量扫描，返回是否真正完成）；`deferred_enqueue` 读取其产出的 open 重复组（harness `CorpusDedupGovernor.blocking_open_groups`）
- `app/api/integrations/google_workspace_oauth.py` — OAuth 成功默认开 Gmail sync
- `app/services/onboarding/second_brain_preset` — preset Gmail 默认 + cron id remap
- `app/api/wiki/sources.py` — REST（agent_id query）+ manual sync + state
- `app/core/cron/adapters/wiki_router_job_runner.py` — Cron router 执行体（source sync + ima sync + maintain）
- `app/api/wiki/routes/ima.py` — ima REST（`/sources/ima/*`）
