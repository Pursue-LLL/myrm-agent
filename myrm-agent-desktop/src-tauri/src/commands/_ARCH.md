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
| `pet_surface.rs` | 核心 | 透明置顶 `/pet-overlay` webview；bounds/show/hide/ignore/focus/toggle | ✅ |
| `session_window.rs` | 核心 | 多会话 CLI 二级 webview | ✅ |
| `visual_approval_overlay.rs` | 核心 | 视觉审批 overlay | ✅ |
| `mod.rs` | 辅助 | 模块导出 | — |

Pet-surface webview 仅允许调用：`pet_surface_set_ignore_cursor`、`pet_surface_set_focusable`、`pet_surface_focus_main_window`、`pet_surface_toggle_main_window`（见 `ipc_security/policy.rs`）。
