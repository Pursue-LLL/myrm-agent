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
| `config.rs` | 核心 | 系统配置读写与数据目录迁移协调入口；`save_system_config`/`reset_system_config` 先写 `desktop_runtime.json` 离席桥，配置落盘或 reset 失败则回滚 runtime（迁移/回滚路径重启后端后统一 `spawn_backend_monitors` 重挂健康监控） | ✅ |
| `desktop_runtime_state.rs` | 核心 | 离席授权 runtime 桥：`desktop_runtime.json` 原子读写（`MYRM_DESKTOP_RUNTIME_FILE`）；server `locked_use_enabled()` 运行时读此文件，保存设置无需重启 Sidecar | ✅ |
| `data_migration.rs` | 核心 | 数据目录迁移预检、流式同步（含逐条目进度回调与拷贝后体积对账）与自愈容灾引擎 | ✅ |
| `pet_surface.rs` | 核心 | 透明置顶 `/pet-overlay` webview；bounds/show/hide/ignore/focus/toggle。页面地址由 `ProductOrigin` 构造的完整产品页地址（`WebviewUrl::External`）：发布版的 `WebviewUrl::App` 会回落到壳页并丢弃路径 | ✅ |
| `session_window.rs` | 核心 | 多会话 CLI 二级 webview，页面为产品页来源上的 `/<session_id>?mode=focused`（`WebviewUrl::External`；会话 ID 经百分号编码，逃不出所在路径段） | ✅ |
| `visual_approval_overlay.rs` | 核心 | 视觉审批 OS 高亮 overlay（macOS 同步建窗；Windows UI 线程异步建窗；其它平台 Err；前端 gate）：屏幕/图像坐标映射到最匹配显示器，在其上开透明置顶的点击穿透窗口。screen / image 模式各自用 payload 的 screen 或 viewport 尺寸与选中 monitor 比对，偏差 >5% 时 fail-closed 不建窗，返回 `{ degraded: true, reason: screen_dimension_mismatch }`（聊天内 bbox 仍为权威）；每次 show 以全新 label 建窗、先建新窗再销毁旧窗；hide 按 label 前缀全部销毁。窗口不受应用级窗口策略管辖（`is_overlay_label`）。窗口点击穿透，故不进截图排除集 | ✅ |
| `visual_approval_overlay_page.rs` | 核心 | 审批高亮页面：自定义协议 `myrm-overlay` 的入口 URL（框几何与标签全在查询参数里，页面无状态、窗口间不串页）、HTML 模板与协议响应（`app/chain.rs` 注册协议）；参数缺失或非法时返回透明占位页 | ✅ |
| `recovery.rs` | 核心 | 崩溃状态收集与恢复 IPC | ✅ |
| `screen_lock.rs` | 核心 | Locked Use 解锁凭据 IPC：Keychain 存/查/删与平台能力查询（含 Windows `RtlGetVersion` 帷幕 WDA build 探测；锁检测在进程内，解锁由 server 执行，均不经 IPC） | ✅ |
| `privacy_curtain.rs` | 核心 | 工位防窥帷幕：每显示器置顶黑幕窗口（全空间可见、黑底防闪白）、输入守卫（回锁经系统确认后才交还租约位）、`relock_outstanding_lease` 壳退出前租约仍未交还时兜底回锁；重建先建新一代窗口再拆旧一代（label 带代号），失败时旧窗原样保留；窗口生命周期托管应用激活策略（仅 deploy/close 两处）；帷幕窗不受应用级窗口策略管辖（`is_curtain_label`，见 `app/setup.rs`） | ✅ |
| `privacy_curtain_page.rs` | 核心 | 帷幕看板页面：文案缓存、HTML 模板、自定义协议 `myrm-curtain` 的 URL 与响应（`app/chain.rs` 注册协议）。页内 IPC 只有 Local 来源才被 ACL 放行，所以页面走自定义协议而非 `data:` URL（共用原语与原因见 `utils/protocol_page.rs`） | ✅ |
| `privacy_curtain_presentation.rs` | 核心 | 帷幕窗口呈现层（macOS 跨 Space / 菜单栏覆盖）：建窗前切 Accessory、窗口抬到菜单栏之上（objc2 `setLevel:`）、销毁后按主窗口在场事实恢复策略（不无条件 Regular，兼容托盘常驻）；非 macOS 全为空实现 | ✅ |
| `privacy_curtain_state.rs` | 核心 | 帷幕状态桥：`curtain_state.json` 的 Tauri 侧唯一读写入口（`CurtainState`，整文件原子替换，读者不会读到撕裂文档），含并发撕裂读回归测试 | ✅ |
| `privacy_curtain_watcher.rs` | 核心 | 锁屏 watcher：1s tick 执行纯决策表 `decide`（自动拉/收帷幕、server 租约电平保持帷幕、显示器热插拔重建——锁屏态与持租约态均跟随，决策表含单测）；自动拉起只置 `active`/`auto_engaged`，不写静默期基准（锁屏不是帷幕上的物理输入）；配置缓存 30s 刷新、启动时清除上一进程遗留状态 | ✅ |
| `mod.rs` | 辅助 | 模块导出 | — |

Pet-surface webview 仅允许调用：`pet_surface_set_ignore_cursor`、`pet_surface_set_focusable`、`pet_surface_focus_main_window`、`pet_surface_toggle_main_window`（见 `ipc_security/policy.rs`；Tauri ACL 授权由同一份策略推导，见 `ipc_security/capability.rs`）。
Curtain webview 仅允许调用：`curtain_report_physical_input`（见 `ipc_security/policy.rs`）。
