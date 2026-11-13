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
| `autostart.rs` | 系统登录项（开机自启）的唯一写入口 `sync_login_item`，启动、保存设置、重置设置三处共用。开发构建（`debug_assertions`）一律不读不写：登录项登记的是当前运行的二进制路径、且只在条目缺失时才写，开发构建抢先登记会让之后安装的正式版也改不回来；发布构建只在条目与开关不一致时才写。策略与系统调用之间隔一个 `LoginItem` trait，测试用记录调用的替身覆盖开发构建零调用、发布构建按开关启停、已一致不重写、读取失败不动、写入被拒只尝试一次，不触碰真实系统；另用产品插件链起一个 `MockRuntime` 应用，证明 `sync_login_item` 与产品注册的 autostart 插件状态接得上（请求值取自当前状态，任何构建下都不会改动测试机器的真实登录项） |
| `setup.rs` | `on_setup` / `on_window_event`：配置、产品页来源 `ProductOrigin` 与 ACL 能力注册（配置载入后、任何产品页发起 IPC 之前）、Sidecar 自启（Next 始终；Python 在 Remote 跟随态 defer）、托盘、隐私帷幕 watcher spawn；启动失败 emit `backend-start-failed` / `frontend-start-failed`；后端启动成功后经 `runtime::spawn_backend_monitors` 统一挂载 watchdog+wake。`on_window_event` 的应用级窗口策略（关闭到托盘、窗口销毁即优雅停机）不管辖帷幕与审批高亮覆盖层（`governs_app_lifecycle`）：它们按需建、用完即销，被拦成隐藏窗会翻转 Dock 策略，被销毁则会被误当作应用退出 |
| `shortcut_handler.rs` | 全局快捷键事件分发 |
| `linux_gpu.rs` | Linux NVIDIA + Wayland WebKitGTK 兼容 |
| `menu.rs` | 原生应用主菜单与 Edit 快捷键桥接（macOS AppKit / Win32 Responder Chain） |
| `tray.rs` | 系统托盘菜单、状态 tooltip、隐私帷幕切换项、IPC `set_tray_status`。托盘图标是模板图标（macOS 随菜单栏深浅自动着色），换图一律经 `apply_tray_icon`：底层 `set_icon` 会重置模板标志，不恢复则图标按纯黑像素显示、在深色菜单栏上看不清；换图与恢复在同一个主线程任务里完成并等任务结束：分开执行时界面会渲染中间状态，图标闪一帧纯黑；托盘句柄是非原子引用计数，任务先释放自己的副本再唤醒调用方，不等任务会让两个线程同时改引用计数（`test_desktop_tray_icon.py` 钉住） |
| `lifecycle.rs` | 优雅停机：`SHUTDOWN_INITIATED` 防重入 + `graceful_stop_backend`（停 monitors → 服务端 drain → 等待自退 → 兜底强杀）+ Sidecar 有序关闭；后端停止后代解锁租约仍未交还则 `relock_outstanding_lease` 兜底回锁（帷幕窗口随进程消失，不能留下解锁态桌面） |

## 依赖

- `runtime` / `commands` / `config` / `utils`
