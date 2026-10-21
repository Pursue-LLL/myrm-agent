# app 模块架构

[INPUT]
- commands / runtime / config / utils 各模块
- Tauri Builder 插件注册表

[OUTPUT]
- run(): 应用主循环、IPC handler、托盘、优雅停机
- chain: 产品插件链与页面协议的共享装配（生产与测试同源）

[POS]
Tauri 应用组装层；main.rs 唯一委托目标。

## 架构概述

Tauri 应用组装层：插件注册、全局快捷键分发、`setup` 钩子、窗口事件、IPC handler 清单、统一 IPC sender gate、托盘与优雅停机。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 职责 |
|------|------|
| `mod.rs` | `run()`：Builder 链（单实例 / 窗口状态 → `chain` 的产品插件与页面协议 → 全局快捷键）、基于 `command_registry_macro.in` 的 `generate_handler`、退出优雅停机 |
| `chain.rs` | 产品插件链（`with_product_plugins`）与页面自定义协议（`with_page_protocols`：帷幕看板 `myrm-curtain`、审批高亮 `myrm-overlay`）的共享装配，对 `Runtime` 泛型：`run()` 与进程内测试走同一条链。单实例、窗口状态、全局快捷键依赖真实桌面会话，留在 `run()`。测试用真实 `generate_context!()` 起一个 `MockRuntime` 应用，证明发布配置被每个插件接受（插件配置多为 `deny_unknown_fields`，错键即启动 panic——并有一条故意放入错键的反例证明该测试会失败），并校验 `plugins.shell.open` 链接白名单 |
| `setup.rs` | `on_setup` / `on_window_event`：配置、产品页来源 `ProductOrigin` 与 ACL 能力注册（配置载入后、任何产品页发起 IPC 之前）、Sidecar 自启（Next 始终；Python 在 Remote 跟随态 defer）、托盘、隐私帷幕 watcher spawn；启动失败 emit `backend-start-failed` / `frontend-start-failed`；后端启动成功后经 `runtime::spawn_backend_monitors` 统一挂载 watchdog+wake。`on_window_event` 的应用级窗口策略（关闭到托盘、窗口销毁即优雅停机）不管辖帷幕与审批高亮覆盖层（`governs_app_lifecycle`）：它们按需建、用完即销，被拦成隐藏窗会翻转 Dock 策略，被销毁则会被误当作应用退出 |
| `shortcut_handler.rs` | 全局快捷键事件分发 |
| `linux_gpu.rs` | Linux NVIDIA + Wayland WebKitGTK 兼容 |
| `menu.rs` | 原生应用主菜单与 Edit 快捷键桥接（macOS AppKit / Win32 Responder Chain） |
| `tray.rs` | 系统托盘菜单、状态 tooltip、隐私帷幕切换项、IPC `set_tray_status` |
| `lifecycle.rs` | 优雅停机：`SHUTDOWN_INITIATED` 防重入 + `graceful_stop_backend`（停 monitors → 服务端 drain → 等待自退 → 兜底强杀）+ Sidecar 有序关闭；后端停止后代解锁租约仍未交还则 `relock_outstanding_lease` 兜底回锁（帷幕窗口随进程消失，不能留下解锁态桌面） |

## 依赖

- `runtime` / `commands` / `config` / `utils`
