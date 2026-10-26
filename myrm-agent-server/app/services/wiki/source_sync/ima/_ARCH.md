# source_sync/ima/

## 架构概述

腾讯 ima 知识库与笔记的**只读**导入连接器：ima OpenAPI → 台账（逐条状态）→ 转 Markdown → `publish_raw` → wiki `raw/ima/`。零 LLM；不写、不删用户的 ima 数据。凭证账号级加密存储，同步按 agent scope 隔离。

同步走 Cron 原生通道：每个 agent 一个 INTERVAL router job（命令 `__wiki_ima_sync__`），每次执行一个**时间盒切片**（约 5 分钟），未完成时用 `JobResult.retry_at` 自续跑，限流/故障退避同样经 `retry_at`，不计失败。重启、暂停、切片超时都从持久化游标继续。

上级文档：[../_ARCH.md](../_ARCH.md)

## 数据流

`inventory`（BFS 遍历文件夹树 + 笔记，写台账，标记 generation，远端消失只标 `remote_deleted`）→ `fetch`（`pending` 行并发导入，每条落到唯一终态）→ 一轮结束 `backfill_complete`。首轮回填完成前不自动编译；之后仅新增/变更条目按用户的 `auto_compile` 入队，且发布时只暂扣（`../deferred_enqueue.py`，持久账本），切片内先做增量 dedup 扫描再放行：落入待审 EXACT/NORMALIZED 重复组的条目留在 Duplicate Review，用户处理后幸存文档自动入队编译，避免同一文档被编译两次。变更用户选择的库（`ImaSyncConfig.fingerprint()` 变化）会重启 inventory。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 对外导出 cron 入口、用户操作、状态读取与错误类 | ✅ |
| `errors.py` | 类型 | `ImaError` 层级；`kind` 是持久化与 UI 文案映射的稳定键，引擎仅凭 `kind` 决定重试/暂停/放弃。`ImaAuthError` 只代表「这次请求被拒」（ima 对密钥失效与「密钥有效但无权读这一项」同样答复）；`ImaPermissionError`（`kind="permission"`，`ImaPermanentError` 子类）是 ima 文档化的「密钥有效但不能读这条」业务码 | ✅ |
| `models.py` | 类型 | ima 松散响应的类型化视图与解析器（唯一知道字段拼写的位置）；媒体类型常量；笔记条目两种拼写都读（嵌套 `basic_info.docid` 与扁平 `note_id` + `note_ext_info`）；笔记页里一条都读不出来时抛 `ImaPermanentError`（形状变了，不当成「账号没有笔记」） | ✅ |
| `transport.py` | 传输 | `POST https://ima.qq.com/<prefix>/<method>`、凭证头、信封解包、错误分类、瞬时失败退避；origin 为常量。业务码分类：20004/200002/110030 → auth；20002/110021/200001/20005 → rate_limit（后两个来自第三方客户端的实测，厂商文档未列）；110010/100003/210003 → transient；100005/210005/210011/210034 → permission；其余 → permanent。错误消息始终带数字码，日志里能定位未知故障 | ✅ |
| `client.py` | 客户端 | 知识库/笔记方法表（只读）：`verify`/`list_knowledge_bases`/`list_knowledge_page`/`get_media_info`/`get_note_text`/`list_notes_page`（笔记走 `list_note_by_folder_id` 游标列表，空 `folder_id` = 全部笔记，每页 ≤20） | ✅ |
| `media.py` | 下载 | 签名 COS URL 的受限下载：仅 https + 腾讯域白名单（`myqcloud.com` 及其子域，加 ima 自有资源主机 `res-pkb` / `res-skb` 的精确匹配）、禁重定向、不带 ima 凭证、流式字节上限 | ✅ |
| `identity.py` | 标识 | 条目 key（`(kb, 父目录, 标题)`，`media_id` 仅作版本信号；同目录同标题的后到条目改用含 `media_id` 的 fallback key）与 `raw/ima/...` 路径（受 raw gate 路径预算约束；Windows 设备名如 `CON`/`NUL` 的目录段加 `_` 前缀） | ✅ |
| `ledger.py` | 台账 | `ImaLedger`：状态机唯一属主（pending/synced/failed/unsupported/too_large/blocked/dismissed/remote_deleted/duplicate）；用户删除的 raw 视为 `dismissed` 永不复活；同 key 冲突时已拥有行的条目保持原行（列表顺序不会让文档换行），其余先到者占 key、后到者落到 fallback key；计数/报告/重试/编译只读当前所选范围（容器），已取消选择的库行原样保留 | ✅ |
| `state.py` | 状态 | `wikiImaSync`（所选库/笔记开关）与 `wikiImaSyncState`（可续跑 inventory 游标、generation、`backfill_complete`、`needs_reauth`、`config_fingerprint`）的 scoped UserConfig 读写；游标是不透明 token，原样持久化、不设长度上限（上限会让一个超长游标使整份状态无法重载而重置同步） | ✅ |
| `credentials.py` | 凭证 | `imaCredentials`（加密，**不在** `ConfigKey` 中，通用 config 端点读不到）；只暴露掩码后的 client id | ✅ |
| `context.py` | 上下文 | 单切片共享上下文：时间预算 + 节流的 state 持久化（15s）+ 切片内密钥核验 `require_valid_key`（被拒请求是「密钥失效」还是「密钥有效但无权读这一项」靠一次轻量 `verify` 区分，每片至多一次、各 worker 共用；核验自身限流则上抛、核验自身失败则按瞬时失败重试）+ 条目失败汇总（供切片末尾的单行日志） | ✅ |
| `inventory.py` | 阶段 | 可续跑盘点：库文件夹树 BFS（持久化队列）+ 笔记（持久化游标 `notes_cursor`）；仅对干净完成的容器标 `remote_deleted`；列表只在服务端 `is_end` 时算完成（笔记页内全已删不终止），游标缺失/重复而未到 `is_end` 记为该容器失败（不标删）；某个库或笔记通道被拒时先核验密钥——失效则整片停止并要求重连，有效则只丢弃该容器（`failed_containers`，不标删），其余库照常导入 | ✅ |
| `content.py` | 转换 | 单条解析为 Markdown + 保真度标注（`images_remote`/`body_truncated`/`layout_flattened`；笔记纯文本是 ima API 的基线，不计为有损）；复用 `bytes_to_wiki_markdown` 与 `web_fetch`；标题/目录/来源链接等远端文本在写入 frontmatter 前压成单行，换行不能结束或伪造字段 | ✅ |
| `importer.py` | 阶段 | 有界并发导入（3 worker、单条 150s 超时、节流）；每行恰好一个终态；仅「经核验确认密钥失效」的鉴权失败、限流与连续的连接级瞬时失败会停止整池，失效网页只记为该条的失败。密钥有效但被拒的条目记为 `failed`（`permission` / 笔记通道 `notes_permission`，终局，获得授权后可由用户重试）；`ImaPermissionError`（如他人笔记）记为 `unsupported` / `not_owner`（跳过而非失败）；核验本身失败按瞬时失败重试。台账读写失败（认领行或记录结果）同样停池：其余 worker 收尾后才上报 `internal`，切片返回后不留在写台账的后台 worker。每片末尾只写一条 WARNING 汇总（类别计数 + 首个已知原因，含 ima 数字码，不含标题与正文） | ✅ |
| `engine.py` | 引擎 | `run_slice`：idle→inventory→fetch 的相位推进，把失败映射为调度建议（`retry_after_s`）；限流暂停写 WARNING（暂停时长 + ima 数字码）；未预期异常记 `internal` 并退避重试，细节只进日志 | ✅ |
| `job_runner.py` | 入口 | cron 入口 `run_ima_sync_job`：单飞锁、凭证/archiver 装配、延迟入队装配（仅 `backfill_complete` 且 `auto_compile` 时）；顺序固定为 切片 → 增量 dedup（`run_post_sync_dedup_scan`，有未被扫描覆盖的暂扣文件或一轮结束时）→ `await` 放行（`finally`；切片抛错或扫描失败时放行本轮文件）→ ingest 快照 | ✅ |
| `job.py` | Cron | 每 agent 同步 job 的创建/恢复/暂停/批量删除与 `trigger_now`（按 command + agent_id 查找） | ✅ |
| `operations.py` | 操作 | 连接（先校验再存）、断开、选库（名称取自 ima 列表）、启动/暂停/恢复、重试失败、仅编译 ima 已导入文档 | ✅ |
| `report.py` | 读取 | 聚合状态与条目报告（只给原因码，不给原始报错；仅统计当前所选范围，并带上共享的自动编译开关与本轮未能完整读取的所选库名 / 笔记通道 `unreadable`） | ✅ |
| `schemas.py` | 类型 | API 响应契约（`ImaStatus`/`ImaItemView`/`ImaUnreadable`/…） | ✅ |

## 测试

- `tests/services/wiki/source_sync/ima/` — 夹具契约（`httpx.MockTransport`）：信封/错误分类/列表与笔记解析/媒体白名单；台账状态机（同标题条目各占一行且不随列表顺序换行、只统计与重试所选范围）；标识与路径预算；内容解析；引擎切片/续跑/变更追踪/凭证脱敏/库列表停滞不判远端删除/游标任意长度可重载（`test_sync_engine.py`）、笔记通道的游标分页/已删页不终止/跨切片续跑/限流后从游标续跑/停滞、形状异常与无笔记权限不判远端删除（`test_notes_lane.py`）与鉴权/限流/瞬时与永久失败/未知异常的内部退避、取消不被吞（`test_sync_engine_failures.py`，共享 `support.py` 与 `conftest.py` 夹具）；权限语义（`test_permission_gate.py`：被拒请求先核验密钥——库/笔记/条目三个层级、密钥失效仍要求重连、多条被拒共用一次核验、核验自身限流/失败、授权后重试、200001 等限流码暂停而非判失败、限流与失败汇总的日志内容，无已知原因时汇总不带原因标签）；业务码分类与消息带数字码（`test_transport.py`）；导入器终态；认领或记录结果时台账失败都等在途条目收尾再停池（`test_sync_engine_failures.py`）；cron 入口的单飞、入队装配与 扫描 → 放行 → 快照 顺序、切片抛错/扫描失败/扫描被跳过仍放行
- `tests/api/wiki/test_wiki_ima_routes.py` — ima 端点、凭证掩码、通用 config 端点读不到 `imaCredentials`

## 依赖

- `app/services/wiki/source_sync/publish_helpers.py` — `publish_source_markdown`（SUPERSEDE，`caller="settings"`）
- `app/services/wiki/source_sync/deferred_enqueue.py` — 暂扣到 dedup 扫描之后的 compile 入队（持久账本）
- `app/services/wiki/source_sync/content_convert.py` — 文档转换
- `app/services/wiki/_userconfig_scoped.py` — scoped UserConfig 持久化
- `app/services/config/service.py` — 凭证加密存储
- `app/database/models/wiki_source_ledger.py` — 台账表
- `app/core/cron/adapters/{setup,wiki_router_job_runner}.py` — cron 管理器与 `__wiki_ima_sync__` 分发
- `app/api/wiki/routes/ima.py` — REST
