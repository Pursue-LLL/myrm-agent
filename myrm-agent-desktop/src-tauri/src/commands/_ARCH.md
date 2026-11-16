# Tauri IPC commands

[INPUT]
- `ipc_security/` (POS: sender gate + command allowlist)
- `runtime/` (POS: sidecar lifecycle)

[OUTPUT]
- Tauri `#[tauri::command]` handlers registered via `command_registry_macro.in`

[POS]
Leaf IPC command modules invoked from the main webview, session webviews, and pet-surface webview. Sidecar lifecycle registry lives under `runtime/process_registry/` (internal; no renderer IPC).

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `config.rs` | 核心 | 系统配置读写与数据目录迁移协调入口；`save_system_config`/`reset_system_config` 先写 `desktop_runtime.json` 离席桥，配置落盘或 reset 失败则回滚 runtime（迁移/回滚路径重启后端后统一 `spawn_backend_monitors` 重挂健康监控）；保存与重置成功后经 `app::autostart::sync_login_item` 同步系统登录项（开发构建不碰）；迁移的源目录经 `utils::data_dir` 解析，目录由 `MYRM_DESKTOP_DATA_DIR` 或开发构建固定时 `migrate_data_dir` 直接拒绝 | ✅ |
| `global_shortcut.rs` | 核心 | 全局快捷键更新命令：注销全部旧快捷键后重新注册 toggle / appshot / voice PTT / inline input，任一注册失败即回滚到旧配置，保证原子性 | ✅ |
| `desktop_runtime_state.rs` | 核心 | 离席授权 runtime 桥：`desktop_runtime.json` 原子读写（`MYRM_DESKTOP_RUNTIME_FILE`）；server `locked_use_enabled()` 运行时读此文件，保存设置无需重启 Sidecar | ✅ |
| `data_migration.rs` | 核心 | 数据目录迁移预检、流式同步（含逐条目进度回调与拷贝后体积对账）与自愈容灾引擎 | ✅ |
| `pet_surface.rs` | 核心 | 透明置顶 `/pet-overlay` webview；bounds/show/hide/ignore/focus/toggle。页面地址由 `ProductOrigin` 构造的完整产品页地址（`WebviewUrl::External`）：发布版的 `WebviewUrl::App` 会回落到壳页并丢弃路径 | ✅ |
| `session_window.rs` | 核心 | 多会话 CLI 二级 webview，页面为产品页来源上的 `/<session_id>?mode=focused`（`WebviewUrl::External`；会话 ID 经百分号编码，逃不出所在路径段） | ✅ |
| `visual_approval_overlay.rs` | 核心 | 视觉审批 OS 高亮 overlay（macOS 同步建窗；Windows UI 线程异步建窗；其它平台 Err；前端 gate）：屏幕/图像坐标映射到最匹配显示器，在其上开透明置顶的点击穿透窗口。screen / image 模式各自用 payload 的 screen 或 viewport 尺寸与选中 monitor 比对，偏差 >5% 时 fail-closed 不建窗，返回 `{ degraded: true, reason: screen_dimension_mismatch }`（聊天内 bbox 仍为权威）；每次 show 以全新 label 建窗、先建新窗再销毁旧窗；hide 按 label 前缀全部销毁。窗口不受应用级窗口策略管辖（`is_overlay_label`）。窗口点击穿透，故不进截图排除集 | ✅ |
| `visual_approval_overlay_page.rs` | 核心 | 审批高亮页面：自定义协议 `myrm-overlay` 的入口 URL（框几何与标签全在查询参数里，页面无状态、窗口间不串页）、HTML 模板与协议响应（`app/chain.rs` 注册协议）；参数缺失或非法时返回透明占位页 | ✅ |
| `recovery.rs` | 核心 | 崩溃状态收集与恢复 IPC；操作的数据目录经 `utils::data_dir` 解析，与后端使用的是同一个目录；`export_local_sqlite` 导出服务端主库 `data.db` 及其 `-wal` / `-shm`，目标必须是已存在的目录且不能是数据目录本身（文件复制到自身会被清空） | ✅ |
| `screen_lock.rs` | 核心 | Locked Use 解锁凭据 IPC：Keychain 存/查/删与平台能力查询（含 Windows `RtlGetVersion` 帷幕 WDA build 探测；锁检测在进程内，解锁由 server 执行，均不经 IPC） | ✅ |
| `privacy_curtain.rs` | 核心 | 工位防窥帷幕：每显示器置顶黑幕窗口（全空间可见、黑底防闪白）、输入守卫（回锁经系统确认后才交还租约位）、`relock_outstanding_lease` 壳退出前租约仍未交还时兜底回锁；重建先建新一代窗口再拆旧一代（label 带代号），失败时旧窗原样保留；窗口生命周期托管应用激活策略（仅 deploy/close 两处）；帷幕窗不受应用级窗口策略管辖（`is_curtain_label`，见 `app/setup.rs`）；状态读不到或没写进去时 `show_privacy_curtain` / `hide_privacy_curtain` / `privacy_curtain_active` 返回 Err，不谎报成功或「未拉起」（手动拉起失败只撤销本次新建的窗口、已在的帷幕不动；清租约位失败则位保持置位） | ✅ |
| `privacy_curtain_decision.rs` | 核心 | 锁屏 watcher 的纯决策表：`TickFacts`（一个 tick 观测到的外部事实）→ `TickAction`；不依赖 Tauri、不带记忆，所以状态没记下的动作下个 tick 会被同样的决策重做（含单测）；自动拉起的状态迁移不写静默期基准（锁屏不是帷幕上的物理输入） | ✅ |
| `privacy_curtain_page.rs` | 核心 | 帷幕看板页面：文案缓存、HTML 模板、自定义协议 `myrm-curtain` 的 URL 与响应（`app/chain.rs` 注册协议）；模板内含 `prefers-reduced-motion: reduce` 守卫（该页是独立文档，前端样式表的守卫到不了它）。页内 IPC 只有 Local 来源才被 ACL 放行，所以页面走自定义协议而非 `data:` URL（共用原语与原因见 `utils/protocol_page.rs`） | ✅ |
| `privacy_curtain_presentation.rs` | 核心 | 帷幕窗口呈现层（macOS 跨 Space / 菜单栏覆盖）：建窗前切 Accessory、窗口抬到菜单栏之上（objc2 `setLevel:`）、销毁后按主窗口在场事实恢复策略（不无条件 Regular，兼容托盘常驻）；非 macOS 全为空实现 | ✅ |
| `privacy_curtain_state.rs` | 核心 | 帷幕状态桥：`curtain_state.json` 的 Tauri 侧唯一读写入口（`CurtainState`）。「读不到」不等于「没有状态」：文件不存在或内容无效 = 默认状态，瞬时错误重试耗尽 = 未知（`try_read_state` 返回 `None`）；读-改-写（`mutate_state`，进程内串行化）在未知时放弃写入并返回 false，绝不拿默认值覆盖读不出来的真实状态（那会清掉 server 的租约位与静默期基准）；`reset_state` 是启动清理在读不到时的自愈出路 | ✅ |
| `privacy_curtain_state_io.rs` | 核心 | 状态文件的落盘原语：带重试的读取（`Document` 三态：有内容 / 没有可用内容 / 读不到）与原子整文件替换（临时文件 + 改名，失败不留临时文件）；Windows 上另一进程替换同一文件时读 / 改名的瞬时拒绝由短重试吸收，含并发撕裂读回归测试 | ✅ |
| `privacy_curtain_state_io_python_tests.rs` | 核心 | 状态文件的跨进程测试，两个方向都用真实 Python 进程做对端：壳读 / Python 写（像 server 的 `os.replace` 持续替换同一个文件，壳按生产的读取与重试预算读取，断言从不读到撕裂文档、「不存在 / 无效」或预算耗尽）；壳写 / Python 读（像 server 的 `read_curtain_state` 持续读，壳用生产的 `replace_document` 持续替换，断言读者从不读到撕裂文档或「不存在」、读取出错只允许是 Windows 上与改名相撞的 `PermissionError`，壳的每次写入都落盘）；两个方向都打印读写遇到的错误种类作为该平台的实测；本机没有 Python 时跳过，CI 上没有则失败 | ✅ |
| `privacy_curtain_transition.rs` | 核心 | 拉起 / 收起帷幕时窗口副作用与状态记录的固定顺序，手动命令与 watcher 共用：拉起先落窗口再记状态，没记下就撤销窗口（事实回到动作之前）；收起先收窗口再记状态，没记下由下个 tick 或用户重试补记；`mutate_state` 的 false 在此变成交给调用方的错误（含单测） | ✅ |
| `privacy_curtain_watcher.rs` | 核心 | 锁屏 watcher：1s tick 读状态、取外部事实、按 `decide` 的决策执行副作用（自动拉/收帷幕、server 租约电平保持帷幕、显示器热插拔重建——锁屏态与持租约态均跟随）；状态读不到的 tick 整个跳过（不拿默认值决策），恢复可读后的下一个 tick 自然补做；自动拉起只置 `active`/`auto_engaged`（不写静默期基准）；配置缓存 30s 刷新、启动时清除上一进程遗留状态 | ✅ |
| `mod.rs` | 辅助 | 模块导出 | — |

Pet-surface webview 仅允许调用：`pet_surface_set_ignore_cursor`、`pet_surface_set_focusable`、`pet_surface_focus_main_window`、`pet_surface_toggle_main_window`（见 `ipc_security/policy.rs`；Tauri ACL 授权由同一份策略推导，见 `ipc_security/capability.rs`）。
Curtain webview 仅允许调用：`curtain_report_physical_input`（见 `ipc_security/policy.rs`）。
