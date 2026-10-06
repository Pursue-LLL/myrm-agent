# Tauri IPC commands

[INPUT]
- `ipc_security/` (POS: sender gate + command allowlist)
- `runtime/` (POS: sidecar lifecycle)

[OUTPUT]
- Tauri `#[tauri::command]` handlers registered via `command_registry_macro.in`

[POS]
Leaf IPC command modules invoked from the main webview, session webviews, and pet-surface webview.

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `config.rs` | 核心 | 系统配置读写与数据目录迁移协调入口（进度事件 emit、新后端健康失败自动指回；迁移/回滚路径重启后端后统一 `spawn_backend_monitors` 重挂健康监控） | ✅ |
| `data_migration.rs` | 核心 | 数据目录迁移预检、流式同步（含逐条目进度回调与拷贝后体积对账）与自愈容灾引擎 | ✅ |
| `pet_surface.rs` | 核心 | 透明置顶 `/pet-overlay` webview；bounds/show/hide/ignore/focus/toggle | ✅ |
| `session_window.rs` | 核心 | 多会话 CLI 二级 webview | ✅ |
| `visual_approval_overlay.rs` | 核心 | 视觉审批 overlay | ✅ |
| `process_registry.rs` | 核心 | 桌面受管进程注册表查询与定向终止 IPC | ✅ |
| `recovery.rs` | 核心 | 崩溃状态收集与恢复 IPC | ✅ |
| `screen_lock.rs` | 核心 | Locked Use 解锁凭据 IPC：Keychain 存/查/删与平台能力查询（锁检测在进程内，解锁由 server 执行，均不经 IPC） | ✅ |
| `privacy_curtain.rs` | 核心 | 工位防窥帷幕：每显示器置顶黑幕窗口（全空间可见、黑底防闪白）、输入守卫（回锁经系统确认后才交还租约位）；重建先建新一代窗口再拆旧一代（label 带代号），失败时旧窗原样保留；窗口生命周期托管应用激活策略（仅 deploy/close 两处） | ✅ |
| `privacy_curtain_page.rs` | 核心 | 帷幕看板页面：文案缓存、HTML 模板、自定义协议 `myrm-curtain` 的 URL 与响应（`app/mod.rs` 注册协议）。页面不走 `data:` URL：tauri 未开 `webview-data-url`，且 data 页属 Remote 来源、页内 IPC 会被 ACL 拒绝 | ✅ |
| `privacy_curtain_presentation.rs` | 核心 | 帷幕窗口呈现层（macOS 跨 Space / 菜单栏覆盖）：建窗前切 Accessory、窗口抬到菜单栏之上（objc2 `setLevel:`）、销毁后按主窗口在场事实恢复策略（不无条件 Regular，兼容托盘常驻）；非 macOS 全为空实现 | ✅ |
| `privacy_curtain_state.rs` | 核心 | 帷幕状态桥：`curtain_state.json` 的 Tauri 侧唯一读写入口（`CurtainState`，整文件原子替换，读者不会读到撕裂文档），含并发撕裂读回归测试 | ✅ |
| `privacy_curtain_watcher.rs` | 核心 | 锁屏 watcher：1s tick 执行纯决策表 `decide`（自动拉/收帷幕、server 租约电平保持帷幕、显示器热插拔重建——锁屏态与持租约态均跟随，决策表含单测）；自动拉起只置 `active`/`auto_engaged`，不写静默期基准（锁屏不是帷幕上的物理输入）；配置缓存 30s 刷新、启动时清除上一进程遗留状态 | ✅ |
| `mod.rs` | 辅助 | 模块导出 | — |

Pet-surface webview 仅允许调用：`pet_surface_set_ignore_cursor`、`pet_surface_set_focusable`、`pet_surface_focus_main_window`、`pet_surface_toggle_main_window`（见 `ipc_security/policy.rs`）。
Curtain webview 仅允许调用：`curtain_report_physical_input`（见 `ipc_security/policy.rs`）。
