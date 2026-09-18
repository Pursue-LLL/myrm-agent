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
| `config.rs` | 核心 | 系统配置读写与数据目录迁移协调入口（进度事件 emit、新后端健康失败自动指回） | ✅ |
| `data_migration.rs` | 核心 | 数据目录迁移预检、流式同步（含逐条目进度回调与拷贝后体积对账）与自愈容灾引擎 | ✅ |
| `pet_surface.rs` | 核心 | 透明置顶 `/pet-overlay` webview；bounds/show/hide/ignore/focus/toggle | ✅ |
| `session_window.rs` | 核心 | 多会话 CLI 二级 webview | ✅ |
| `visual_approval_overlay.rs` | 核心 | 视觉审批 overlay | ✅ |
| `process_registry.rs` | 核心 | 桌面受管进程注册表查询与定向终止 IPC | ✅ |
| `power.rs` | 核心 | 节能与睡眠抑制控制 IPC | ✅ |
| `recovery.rs` | 核心 | 崩溃状态收集与恢复 IPC | ✅ |
| `screen_lock.rs` | 核心 | 屏幕锁定感知与隐私保护 IPC | ✅ |
| `mod.rs` | 辅助 | 模块导出 | — |

Pet-surface webview 仅允许调用：`pet_surface_set_ignore_cursor`、`pet_surface_set_focusable`、`pet_surface_focus_main_window`、`pet_surface_toggle_main_window`（见 `ipc_security/policy.rs`）。
