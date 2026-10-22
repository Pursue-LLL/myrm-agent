# services/instance_archive/

## 架构概述

整实例（一个用户的全部状态目录）的导出、导入与恢复点。业务策略层：决定**什么随备份走、什么留在目标主机、密钥如何受保护、换入如何排队并在启动前原子生效**。通用机制（一致性 SQLite 快照、zip+manifest、校验解包、带日志的可崩溃恢复换入）在 harness `infra/state_archive/`，本目录只做策略与编排，不重复实现机制。

核心约束（代码为准）：

- **运行中的进程永不写入自己持有的文件**：导入/恢复只在 staging 中校验并写 pending marker，真正的换入在 lifespan 中、`init_database` 之前由 `promotion_hook.run_pending_promotion` 完成。
- **默认包含（include-by-default）**：未分类的新数据存储默认随备份走，避免静默丢数据；密钥、主机身份、可重建索引、运行态文件由 `policy._EXCLUDED_TOP_LEVEL` 显式排除。CI 对账测试把 `table_policy` 中每个名字钉到真实 schema，改名不会悄悄使策略失效。
- **每个 SQLite 各自时点一致，但依次采集**：`data.db`、向量库各集合、记忆库不是跨库原子快照；备份期间仍在写入的内容可能只出现在其中一份。普通文件按读取时的磁盘状态入包（见 `state_archive` 契约）。
- **读不到的数据项如实报告，不悄悄少带**：扫描遇到无法列出的目录、无法读取的文件，会把路径放进 `StateScan.unreadable`，导出结果以 `ExportResult.unreadable` 汇总（扫描时读不到的，加上写入时被跳过且此刻仍存在的；扫描后才消失的文件是正常的并发变化，不计入）。手动导出把数量交给界面提示，定时备份据此记失败，见 [`auto_backup/_ARCH.md`](auto_backup/_ARCH.md)。
- **备份自带“不完整”声明，恢复预览如实告知**：导出把上述净数量写入 manifest 元数据 `unreadable_count`（harness 写入器自己记的 `skipped` 是含已消失文件的原始记录，两者口径不同：前者是服务端的净判定）。整目录替换会移除正在运行的实例里备份没有的内容，所以 stage 读出该数量放进 `ImportReport.unreadable_count`，界面给出非阻断的警示。归档不可信，读取按“必须是非负整数、上限 100 万”处理，其余一律视为 0；旧归档无该字段同样视为 0。
- **恢复点只回退数据库**（`data.db` + `checkpoints.db`）：GB 级向量库不随恢复点回退；整实例备份才携带它。恢复点是本机的原样回退保险，不做 scrub：创建时尚存的无痕会话会留在点里，直到该点被保留策略清理或手动删除。
- **归档是不可信输入**：导出方声明的一切在 stage 阶段被重新强制（路径白名单、表/配置行策略、schema 版本闸门）。
- **覆盖前可比对**：导入报告的 `created_at` 是备份生成时间（取自 manifest）；`counts`（备份）与 `current_counts`（运行中实例的同名表，读不到则为空）并排给出，计数键即前端渲染键（`stage_db._SUMMARY_TABLES`）；两侧用同一口径计数，聊天只计应用列表可见的（不含回收站与无痕会话）。
- **只暴露稳定机器码**：错误用 `code`、再入凭据用 `reentry` 标识（`config:<key>` / `table:<name>` / `path:<file>`），用户可见文案全部在前端 locale。

## 数据分类规则

| 类别 | 行为 | 例 |
|------|------|-----|
| DATA | 随备份走 | 会话、消息、智能体、技能、wiki、记忆（含内嵌向量库 `qdrant/`：语义/情景记忆正文只存在于其中）、cron、工作区文件 |
| SECRET | 不进归档，恢复后由用户重新登录/填写 | `session_vault`、`agent_secrets`、`vault_credentials`、渠道登录态（`whatsapp_auth`、`matrix`） |
| MACHINE_KEY | 不进归档，目标机保留或自行生成，用户无需操作 | `.encryption_key`、`vault.key` |
| HOST_BOUND | 目标主机保留自己的（归档不会放宽目标安全姿态） | 工具白名单、风险规则、审批、配对、API key、`channelInstances` 等配置行 |
| EPHEMERAL | 清空 | 分享链接、离线持久任务、中断回合标记 |
| 网页无痕会话 | 不进归档：整条会话连同消息、全文索引、回忆索引、只按会话 id 记录的普通表行（`CHAT_BOUND_TABLES`）一并删除（`source = 'web'` 且 `is_incognito = 1`），`checkpoints.db` 里该会话的 checkpoint 线程（含两个别名）同样删除；工具在无痕会话里不受限，它在 `harness/workspaces/chat_<id>/`（含其产物保险库）下写的文件同样不进导出，会话取自导出当下的在线库；无痕会话绑定的上传（sidecar 的 `source_chat_id`）及其 PDF 页图、其会话尚无行或已不存在的绑定上传同样不进导出（判据是会话的实际状态：绑定的会话是归档保留的会话时照常携带；前端切换无痕必然开新会话，绑定不会落在可被关掉的旧会话上）；会话转写导入（`source` 非 web）借用无痕标记只为不进侧栏，是真实数据，照常携带 | 导出、定时备份、导入暂存共用 `scrub_sensitive_surface` 与 `checkpoint_scrub`；工作区文件与绑定上传只在导出端由 `incognito_workspaces` / `incognito_uploads` 筛掉 |
| IDENTITY | 仅当导入身份 = 导出身份时携带 | `commitments`、技能权限使用日志、产物审计日志 |
| DERIVED / RUNTIME / LOCAL_HISTORY | 不进归档 | `skill_scans`、locks、cache、logs、snapshots、`subagent_checkpoints.sqlite`（按文件名识别：目录由部署决定，内容按任务而非按会话记录，线程重启后不可恢复） |
| PORTABLE_SECRET | 仅在口令信封下以**原密文**携带（`providers`、`retrieval`、`searchServices`、`mcpServers`、`mcpOAuthTokens`） | 导出时用户设置口令；信封只包裹 32 字节配置密钥，归档内无明文 |

导入后：计划任务一律以暂停态进入；携带的密钥重新加密到目标主机；含可执行内容（定时命令、MCP stdio、技能脚本）须用户显式确认信任。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出契约与三条用户流程入口（含 pre-boot 换入入口） | ✅ |
| `models.py` | 核心 | 工作目录布局（`{state_dir}/instance_archive`）、pending marker、一次性 outcome、ImportReport 契约 | ✅ |
| `policy.py` | 核心 | 路径分类：导出扫描（`scan_state_dir` 返回 `StateScan`：入包来源、被排除项、读不到的路径）、导入侧白名单、换入计划共用同一分类器；顶层名之外还按文件名排除目录由部署决定的运行时库（`_RUNTIME_FILE_NAMES`，当前是子代理 checkpoint 库，其文件名被 `test_incognito_files.py` 钉到 harness 的路径解析）；`is_standard_layout` 判定状态目录与数据库是否为标准布局（整实例备份的前提） | ✅ |
| `table_policy.py` | 核心 | data.db 表/配置行策略（HOST_BOUND/SECRET/EPHEMERAL/IDENTITY/PORTABLE_SECRET）与对每份归档副本的 scrub（含网页无痕会话的删除：先清 `CHAT_BOUND_TABLES` 里按会话 id 记录的行，再靠 `ON DELETE CASCADE` 删会话，故在提交后临时开启 `foreign_keys` 并回读确认，开启失败则整个导出/暂存失败，不留孤儿消息；`web_incognito_chat_ids` 供 data.db 之外按会话 id 存放的库使用，`live_web_incognito_chat_ids` 以只读连接读在线库当下的名单，读不到就抛错、不当作“没有无痕会话”；`live_surviving_chat_ids` 同样读在线库，给出归档保留的全部会话，供文件库判断绑定上传的会话是否还在） | ✅ |
| `checkpoint_scrub.py` | 核心 | `checkpoints.db` 副本里网页无痕会话的 checkpoint 线程（每个会话两个别名，取自运行时的 `resolve_thread_ids`）：清除所有带 `thread_id` 列的表并开启 `secure_delete`；导出用 `live_checkpoint_scrubber`（会话取自拷贝那一刻的在线 data.db，清除失败则该库不入包并如实报告），导入暂存在 `stage_db` 里对紧邻的 `checkpoints.db` 调用 | ✅ |
| `incognito_workspaces.py` | 核心 | 导出端把网页无痕会话的工作区目录（`harness/workspaces/chat_<id>/`，目录名取 `CHAT_SESSION_PREFIX` + 会话 id，整段路径分量比对，`chat_a` 不会藏掉 `chat_ab`）从扫描结果里去掉，连同这些目录下读不到的路径一起去掉（有意不带，不能让备份显得不完整）；会话名单在扫描之后读取，读不到则导出失败，不会带着全部工作区继续 | ✅ |
| `incognito_uploads.py` | 核心 | 导出端把绑定到“归档不保留的会话”（网页无痕或已不存在）的上传从扫描结果里去掉：读 `storage/files/**.meta.json` 的 `source_chat_id`，选择规则用 `core.storage.chat_bound` 的纯函数（与保留任务同一套），连带其 PDF 页图与两类 sidecar；读不到的 sidecar 连同其文件一起去掉并记入 `unreadable`（不猜测）；损坏的 sidecar（应用自己也会跳过）照常携带；归档保留的会话名单（`table_policy.live_surviving_chat_ids`）在扫描之后读取，读不到则导出失败，不会带着全部绑定上传继续 | ✅ |
| `envelope.py` | 核心 | 口令信封：scrypt 派生包裹密钥，封存/解封配置加密密钥（KDF 参数来自不可信归档，使用前设界） | ✅ |
| `export_service.py` | 核心 | 同步导出流水线（工作线程）：流式写 zip，data.db 用 VACUUM INTO 快照后 scrub、`checkpoints.db` 快照后清除无痕线程、无痕会话的工作区文件与绑定上传在扫描阶段就不入包；结果带回读不到的路径（`ExportResult.unreadable`），并把数量写入 manifest `unreadable_count` | ✅ |
| `export_jobs.py` | 核心 | 后台导出任务：进度、取消、TTL 清理、同一时刻仅一个导出；`get_export_manager` 按状态目录登记唯一实例（手动导出与定时备份共用同一闸门），`ExportJob.done` 供同步等待，`is_busy` 供只读判断 | ✅ |
| `auto_backup/` | 子包 | 本地/桌面定时整实例备份（默认关闭）：复用导出流水线写到用户选择的文件夹、保留最近 N 份、连续失败告警；见 [`auto_backup/_ARCH.md`](auto_backup/_ARCH.md) | ✅ |
| `uploads.py` | 核心 | 可续传分块上传：固定块大小按偏移写入预分配文件，无拼接与二次拷贝 | ✅ |
| `import_service.py` | 核心 | 导入 stage / confirm / cancel：完整性、版本闸门、路径白名单、数据库 scrub/graft、用户报告（备份声明的再入凭据不可信：与暂存发现合并后只留已知前缀、限长、限量；声明的“读不到数量”同样只信非负整数并设上限） | ✅ |
| `stage_db.py` | 核心 | staged data.db 预处理：校验、scrub（同时清理紧邻的 staged `checkpoints.db` 里的无痕线程）、HOST_BOUND 行从 live 库嫁接、定时任务暂停、密钥重加密、摘要 | ✅ |
| `schema_gate.py` | 辅助 | 当前构建可打开的最高 schema 版本，拒绝来自更新版本的库 | ✅ |
| `restore_points.py` | 核心 | 恢复点（更新前快照等）：在线一致性复制、列表/清理、恢复 = 校验后排队下次启动换入 | ✅ |
| `promotion_hook.py` | 核心 | 启动前换入：先恢复被中断的换入，再提升 pending marker；一次性 outcome；撤销（回滚到换入前状态） | ✅ |

## 依赖方向

`app/api/instance_archive/` → 本目录 → `myrm_agent_harness.infra.state_archive`。lifespan 调用 `run_pending_promotion`，调度器每小时调用 `auto_backup.run_auto_backup_tick`。`auto_backup/` 依赖 `export_jobs`、`models`、`policy`，反向无依赖。本目录读取 `core/storage/chat_bound.py`（绑定上传的选择规则）与 `core/storage/paths.py`（sidecar 位置与后缀），以及 `services/chat/chat_bound_rows.py` 的 `CHAT_BOUND_TABLES`（只含表名与列名的纯清单，新增按会话 id 存放的表时只改那一处）与 `platform_utils/workspace_session.py` 的 `CHAT_SESSION_PREFIX`（会话 id 加该前缀即工作区目录名）；不依赖 API 层，harness 不感知本目录。
