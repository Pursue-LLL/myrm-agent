# routes/

Wiki API sub-routers included by `router.py`.

## 架构概述

Extension clip、wikiignore 与 ima 导入 REST 子路由，与 Brain Console 主 router 分离。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 入口 | 子路由包 | — |
| `clip.py` | 路由 | **POST/GET /clip** · **GET/PUT /wikiignore** | ✅ |
| `ima.py` | 路由 | **GET /sources/ima**（聚合状态）· **PUT/DELETE /sources/ima/credentials**（写入前先向 ima 校验；API Key 只写不回显；DELETE 即断开，账号级：停掉所有智能体的同步任务与运行中的切片，再清密钥）· **GET /sources/ima/libraries** · **PUT /sources/ima/config** · **POST /sources/ima/sync/{start,pause,resume,retry-failed}**（`start` 也承担「立即检查」：已有任务则立刻触发下一轮；`pause` 同时让该智能体运行中的切片在下一条处收尾；`retry-failed` 只重排当前所选范围） · **POST /sources/ima/compile**（只编译 ima 已导入且属于当前所选知识库/笔记的文档，与卡片计数口径一致；去重待审 409）· **GET /sources/ima/items?bucket=attention\|lossy\|remote_deleted**；错误一律 `{code, message}`，不透传上游原文；cron 管理器拒绝（`ValueError`）映射为 409 `sync_unavailable`，原因记为 WARNING | ✅ |
| `query.py` | 路由 | **POST /query**（先过风控闸门）· **GET /assets/{filename}** · **POST /compile**（202 入队）· **GET /health-report** | ✅ |
| `dedup.py` | 路由 | **/dedup/\*** 扫描、分组、处置、进度、vault 卫生、回收站恢复与排除撤销 | ✅ |
| `stats.py` | 路由 | **GET /stats** 统计概览 | ✅ |
| `tree.py` | 路由 | **/concepts** 列表与详情、**/tree** 与 **/raw/tree**、目录创建/移动/删除、概念双向链接 | ✅ |
| `mutations.py` | 路由 | **POST /apply** · **POST /compound** · **POST /daily-review** · **POST /templates/seed** · **DELETE /concepts** · **DELETE /raw** | ✅ |
| `queue.py` | 路由 | **/queue** 状态与重试、**/pending** 审批、**/repair-types**、**/repair-publication**、**/reindex-vectors** | ✅ |
| `insights.py` | 路由 | **/purpose**、**/graph/insights**、**/research**、**/ingest**、**/graph** | ✅ |
| `imports.py` | 路由 | **/import/folder** · **/import/zip** · **/import/obsidian** · **/import/obsidian-zip** | ✅ |
| `url_import.py` | 路由 | **POST /import/urls** | ✅ |
| `video_import.py` | 路由 | **POST /import/video** | ✅ |
| `meeting.py` | 路由 | **/meeting-notes/transcribe** 与 **/meeting-notes/live/{session_id}[/ingest|/finalize]** | ✅ |
| `vault.py` | 路由 | **POST /vault/reveal** · **POST /vault/open-obsidian** | ✅ |
| `portability.py` | 路由 | **GET /portability/export** | ✅ |
| `schemas.py` | 契约 | 查询/编译/统计/树/变更/去重模型 | ✅ |
| `schemas_import.py` | 契约 | 批量导入请求与响应模型 | ✅ |
| `vault_effects.py` | 支撑 | 变更后的 vault 索引刷新与认知地图事件 | ✅ |
| `response_mappers.py` | 支撑 | 服务层结果到 API 响应模型的领域映射 | ✅ |
| `import_helpers.py` | 支撑 | 批量导入的 raw 写入、冲突策略校验、结果统计与消息拼装 | ✅ |

## 依赖

- `app.services.wiki.clip` (POS: clip job orchestration + multipart cap)
- `app.services.wiki.source_sync.ima` (POS: ima sync facade)
- `app.services.wiki.vault` (POS: wiki archiver)
- `myrm_agent_harness.toolkits.wiki.pipeline.ingress` (POS: clip ingress + wikiignore)
