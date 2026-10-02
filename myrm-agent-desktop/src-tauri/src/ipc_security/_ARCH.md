# ipc_security 模块架构

[INPUT]
- Tauri invoke 元数据（command / webview label）
- 高敏操作票据申请与确认请求

[OUTPUT]
- IPC sender gate（main/session 来源校验）
- 高敏操作票据与原生确认流程
- `ipc-sensitive-confirmation` 审计事件

[POS]
Desktop IPC 安全边界实现；统一承接命令面授权、拒绝策略与高敏确认。

## 架构概述

策略（policy）、票据（ticket_store）、确认（confirmation）三层构成：命令风险分级与 surface 授权集中在 policy，短时高敏票据与本地化确认各自独立。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 核心 | 模块门面、对外 re-export、Tauri `issue_sensitive_action_ticket` 命令入口 | ✅ |
| `policy.rs` | 核心 | 命令风险分级、main/session/pet/curtain 四信任域策略、`authorize_*` 与 deny 处理 | ✅ |
| `ticket_store.rs` | 核心 | 短时敏感票据存储（TTL/上限/消费） | ✅ |
| `confirmation.rs` | 核心 | 本地化确认文案、原生弹窗确认、确认审计事件 | ✅ |
| `tests.rs` | 核心 | 策略覆盖、票据语义、本地化确认与命令注册一致性测试 | ✅ |
