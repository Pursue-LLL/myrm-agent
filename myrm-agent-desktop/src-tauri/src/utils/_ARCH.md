# utils 模块架构

[INPUT]
- 平台原生 API（CoreGraphics / Win32 / Keychain）

[OUTPUT]
- 锁屏、凭据、隔离修复、OTA pubkey 校验、进程强杀、自定义协议页面原语等系统能力

[POS]
跨平台系统工具封装；由 commands/ IPC 或 app/ 启动期调用。

## 架构概述

跨平台系统能力封装；由 `commands/` 通过 IPC 暴露给前端，或由 `main`/`runtime` 在启动期调用。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 聚合 | 子模块声明 | — |
| `screen_lock.rs` | 核心 | 锁屏进程内检测（macOS CoreGraphics 会话字典 FFI）与系统确认式锁屏请求 | ✅ |
| `screen_credential.rs` | 核心 | Locked Use 登录密码的平台钥匙串存取：密码经 `security -i` 的 stdin 写入（不进 argv），含控制字符拒收、缺失条目删除幂等与真实钥匙串往返 / 进程列表泄漏回归测试（`--ignored`） | ✅ |
| `auth.rs` | 核心 | macOS 提权修复隔离属性 | — |
| `quarantine.rs` | 核心 | com.apple.quarantine 扫描与静默修复 | — |
| `updater_safety.rs` | 核心 | 启动期 OTA pubkey 占位符强校验 | ✅ |
| `process_tree.rs` | 核心 | 进程强杀原语：Windows 递归终止整棵子进程树，POSIX 仅强杀指定 PID（后代由自身退出处理收尾） | ✅ |
| `protocol_page.rs` | 核心 | 自定义协议页面共用原语：入口 URL（`page_url`，含 Windows `http://<scheme>.localhost` 形态与查询参数）、`html_escape`、不缓存的 `html_response`；帷幕看板页与视觉审批高亮页共用，窗口页不走 `data:` URL 的原因记在模块头 | ✅ |

## 依赖

- `tauri` / 平台原生 API
- 发版流程见 [DESKTOP_RELEASE_SYSTEM.md](../../../DESKTOP_RELEASE_SYSTEM.md)
