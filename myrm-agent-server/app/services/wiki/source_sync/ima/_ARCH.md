# source_sync/ima/

## 架构概述

腾讯 ima 知识库与笔记的**只读**导入连接器：ima OpenAPI → 台账（逐条状态）→ 转 Markdown → `publish_raw` → wiki `raw/ima/`。零 LLM；不写、不删用户的 ima 数据。凭证账号级加密存储，同步按 agent scope 隔离。

同步走 Cron 原生通道：每个 agent 一个 INTERVAL router job（命令 `__wiki_ima_sync__`），每次执行一个**时间盒切片**（约 5 分钟），未完成时用 `JobResult.retry_at` 自续跑，限流/故障退避同样经 `retry_at`，不计失败。重启、暂停、切片超时都从持久化游标继续。

上级文档：[../_ARCH.md](../_ARCH.md)

## 数据流

`inventory`（BFS 遍历文件夹树 + 笔记，写台账，标记 generation，远端消失只标 `remote_deleted`）→ `fetch`（`pending` 行并发导入，每条落到唯一终态）→ 一轮结束 `backfill_complete`。首轮回填完成前不自动编译；之后仅新增/变更条目按用户的 `auto_compile` 入队。变更用户选择的库（`ImaSyncConfig.fingerprint()` 变化）会重启 inventory。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 对外导出 cron 入口、用户操作、状态读取与错误类 | ✅ |
| `errors.py` | 类型 | `ImaError` 层级；`kind` 是持久化与 UI 文案映射的稳定键，引擎仅凭 `kind` 决定重试/暂停/放弃 | ✅ |
| `models.py` | 类型 | ima 松散响应的类型化视图与解析器（唯一知道字段拼写的位置）；媒体类型常量 | ✅ |
| `transport.py` | 传输 | `POST https://ima.qq.com/<prefix>/<method>`、凭证头、信封解包、错误分类、瞬时失败退避；origin 为常量 | ✅ |
| `client.py` | 客户端 | 知识库/笔记方法表（只读）：`verify`/`list_knowledge_bases`/`list_knowledge_page`/`get_media_info`/`get_note_text`/`list_notes_page` | ✅ |
| `media.py` | 下载 | 签名 COS URL 的受限下载：仅 https + 腾讯域白名单、禁重定向、不带 ima 凭证、流式字节上限 | ✅ |
| `identity.py` | 标识 | 条目 key（`(kb, 父目录, 标题)`，`media_id` 仅作版本信号）与 `raw/ima/...` 路径（受 raw gate 路径预算约束；Windows 设备名如 `CON`/`NUL` 的目录段加 `_` 前缀） | ✅ |
| `ledger.py` | 台账 | `ImaLedger`：状态机唯一属主（pending/synced/failed/unsupported/too_large/blocked/dismissed/remote_deleted/duplicate）；用户删除的 raw 视为 `dismissed` 永不复活 | ✅ |
| `state.py` | 状态 | `wikiImaSync`（所选库/笔记开关）与 `wikiImaSyncState`（可续跑 inventory 游标、generation、`backfill_complete`、`needs_reauth`、`config_fingerprint`）的 scoped UserConfig 读写 | ✅ |
| `credentials.py` | 凭证 | `imaCredentials`（加密，**不在** `ConfigKey` 中，通用 config 端点读不到）；只暴露掩码后的 client id | ✅ |
| `context.py` | 上下文 | 单切片共享上下文：时间预算 + 节流的 state 持久化（15s） | ✅ |
| `inventory.py` | 阶段 | 可续跑盘点：库文件夹树 BFS（持久化队列）+ 笔记；仅对干净完成的容器标 `remote_deleted` | ✅ |
| `content.py` | 转换 | 单条解析为 Markdown + 保真度标注（`plain_text`/`images_remote`/`body_truncated`/`layout_flattened`）；复用 `bytes_to_wiki_markdown` 与 `web_fetch`；标题/目录/来源链接等远端文本在写入 frontmatter 前压成单行，换行不能结束或伪造字段 | ✅ |
| `importer.py` | 阶段 | 有界并发导入（3 worker、单条 150s 超时、节流）；每行恰好一个终态；仅鉴权失败、限流与连续的连接级瞬时失败会停止整池，失效网页只记为该条的失败 | ✅ |
| `engine.py` | 引擎 | `run_slice`：idle→inventory→fetch 的相位推进，把失败映射为调度建议（`retry_after_s`） | ✅ |
| `job_runner.py` | 入口 | cron 入口 `run_ima_sync_job`：单飞锁、凭证/archiver 装配、发布后 ingest 快照与增量 dedup | ✅ |
| `job.py` | Cron | 每 agent 同步 job 的创建/恢复/暂停/批量删除与 `trigger_now`（按 command + agent_id 查找） | ✅ |
| `operations.py` | 操作 | 连接（先校验再存）、断开、选库（名称取自 ima 列表）、启动/暂停/恢复、重试失败、仅编译 ima 已导入文档 | ✅ |
| `report.py` | 读取 | 聚合状态与条目报告（只给原因码，不给原始报错） | ✅ |
| `schemas.py` | 类型 | API 响应契约（`ImaStatus`/`ImaItemView`/…） | ✅ |

## 测试

- `tests/services/wiki/source_sync/ima/` — 夹具契约（`httpx.MockTransport`）：信封/错误分类/列表与笔记解析/媒体白名单；台账状态机；标识与路径预算；内容解析；引擎切片/续跑/鉴权/限流；导入器终态
- `tests/api/wiki/test_wiki_ima_routes.py` — ima 端点、凭证掩码、通用 config 端点读不到 `imaCredentials`

## 依赖

- `app/services/wiki/source_sync/publish_helpers.py` — `publish_source_markdown`（SUPERSEDE，`caller="settings"`）
- `app/services/wiki/source_sync/content_convert.py` — 文档转换
- `app/services/wiki/_userconfig_scoped.py` — scoped UserConfig 持久化
- `app/services/config/service.py` — 凭证加密存储
- `app/database/models/wiki_source_ledger.py` — 台账表
- `app/core/cron/adapters/{setup,wiki_router_job_runner}.py` — cron 管理器与 `__wiki_ima_sync__` 分发
- `app/api/wiki/routes/ima.py` — REST
