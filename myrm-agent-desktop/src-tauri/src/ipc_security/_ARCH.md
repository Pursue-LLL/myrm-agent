# ipc_security 模块架构

[INPUT]
- Tauri invoke 元数据（command / webview label）
- 高敏操作票据申请与确认请求
- 命令注册表（`command_registry_macro.in`）与产品页来源（`runtime::ProductOrigin`）

[OUTPUT]
- IPC sender gate（main/session 来源校验）
- 产品窗口的 Tauri ACL capability（由 sender gate 推导，Local + 精确来源 Remote）
- 高敏操作票据与原生确认流程
- `ipc-sensitive-confirmation` 审计事件

[POS]
Desktop IPC 安全边界实现；统一承接命令面授权、拒绝策略与高敏确认。

## 架构概述

策略（policy）、能力（capability）、票据（ticket_store）、确认（confirmation）四层构成：命令风险分级与 surface 授权集中在 policy，短时高敏票据与本地化确认各自独立。

一条 IPC 调用要过两道闸门，且必须同时放行：Tauri ACL（在命令入口按「窗口标签 × 来源」放行，授权清单即 `capability.rs`）和应用层 `authorize_request`（`policy.rs`，按窗口面放行）。应用命令的 ACL 授权由 `authorize_request` 逐条推导，没有第二份手写清单，所以两道闸门对任一应用命令的结论一致；本目录只手写内核与官方插件命令的授权，且按最小权限逐条列出。

发布版产品页是 `http://127.0.0.1:<port>`，Tauri 判它为 Remote 来源；开发版直连 `devUrl`，判为 Local。同一份 capability 因此同时声明 Local 与精确来源 Remote（不用通配、端口取启动期配置），开发与发布得到同一张权限表。帷幕窗口的页面走自定义协议（`myrm-curtain`），属 Local，由静态的 `capabilities/curtain.json` 授权，且只放行 `curtain_report_physical_input`；审批高亮窗口（`myrm-overlay`）不发起 IPC，没有任何 capability（`acl_tests` 钉死）。

父模块：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `mod.rs` | 核心 | 模块门面、对外 re-export（含 `register_product_capabilities`）、Tauri `issue_sensitive_action_ticket` 命令入口 | ✅ |
| `policy.rs` | 核心 | 命令风险分级、main/session/pet/curtain 四信任域策略、`authorize_*` 与 deny 处理 | ✅ |
| `capability.rs` | 核心 | 产品窗口面（`main` / `session-*` / `pet-surface`）的 ACL capability：应用命令授权由 `authorize_request` × 命令注册表推导；内核与官方插件命令按前端实际用法最小授权（`fs` / `shell:allow-open` 不配静态 scope）；每个窗口面一份，同时覆盖 Local 与精确来源 Remote；`register_product_capabilities` 在 `setup` 里于首个产品页发起 IPC 之前调用 | ✅ |
| `ticket_store.rs` | 核心 | 短时敏感票据存储（TTL/上限/消费） | ✅ |
| `confirmation.rs` | 核心 | 本地化确认文案、原生弹窗确认、确认审计事件 | ✅ |
| `tests.rs` | 核心 | 策略覆盖、票据语义、本地化确认与命令注册一致性测试 | ✅ |
| `acl_tests.rs` | 核心 | 进程内 ACL 契约测试：真实 `generate_context!()` 的 ACL 清单 + 真实 `capability.rs`，在 `MockRuntime` 上逐条核对「窗口标签 × 来源（Local 壳页 / Remote 产品页 / 自定义协议页）× 命令」，证明 ACL 与 `authorize_request` 一致（含近似标签的负例）、Local 与 Remote 同权、关键命令只属主窗口、帷幕页只能上报物理输入、插件授权与最小权限表一致、异源页面（其他端口、同前缀端口、`localhost`、https、以 `127.0.0.1.` 开头的域名）一概零授权 | ✅ |
