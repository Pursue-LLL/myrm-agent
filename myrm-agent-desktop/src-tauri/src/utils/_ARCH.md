# utils 模块架构

[INPUT]
- 平台原生 API（IOKit / Win32 / systemd-inhibit / Keychain）

[OUTPUT]
- 电源锁、锁屏、隔离修复、OTA pubkey 校验等系统能力

[POS]
跨平台系统工具封装；由 commands/ IPC 或 app/ 启动期调用。

## 架构概述

跨平台系统能力封装；由 `commands/` 通过 IPC 暴露给前端，或由 `main`/`runtime` 在启动期调用。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 聚合 | 子模块声明 | — |
| `power.rs` | 核心 | RAII 电源锁（macOS IOKit / Win32 / systemd-inhibit） | — |
| `screen_lock.rs` | 核心 | 锁屏检测、解锁、Keychain 密码 | — |
| `auth.rs` | 核心 | macOS 提权修复隔离属性 | — |
| `quarantine.rs` | 核心 | com.apple.quarantine 扫描与静默修复 | — |
| `updater_safety.rs` | 核心 | 启动期 OTA pubkey 占位符强校验 | ✅ |

## 依赖

- `tauri` / 平台原生 API
- 发版流程见 [DESKTOP_RELEASE_SYSTEM.md](../../../DESKTOP_RELEASE_SYSTEM.md)
