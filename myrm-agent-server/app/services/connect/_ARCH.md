# services/connect/

## 架构概述

外部 AI Agent（Claude Code、Cursor、Windsurf 等）连接向导：生成 MCP 配置片段、API token、健康检查与连接档案管理。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 | — |
| `profiles.py` | 纯数据 | `ConnectionProfile` 冻结 dataclass + `PROFILES` 注册表（5 个外部 Agent 及其配置文件路径/格式/instructions_key），零依赖 | ✅ |
| `service.py` | 核心 | `ConnectService`：token 签发（携带 agent_id 作用域）、ingress URL 解析、resolve_token 返回 VerifiedConnectToken(profile_id, agent_id)、doctor 健康检查（LOCAL/TAURI 走真实配置文件校验，SANDBOX 诚实降级为 token 存在性；只写 doctor_ok/last_doctor_detail/last_doctor_at，不改 lifecycle status；`last_doctor_detail` 持久化 detail 码供前端三态渲染）、Agent Plugins bundle 生成；`connected_at` 仅由首次 `mark_ready`（真实 MCP 流量）写入 | ✅ |
| `doctor_check.py` | 纯函数 | doctor 核心校验：按 `ConnectionProfile.config_file_path` 读取外部 Agent 磁盘上的 MCP 配置（JSON/TOML），校验 `myrm-memory` 条目存在 + `Authorization` Bearer token 哈希匹配（scheme 大小写不敏感，RFC 9110 §11.1）；识别环境变量令牌引用（`${VAR}`/`${env:VAR}` → `token_env`）与缺失 Authorization（→ `token_missing`），输出 DoctorVerdict(healthy, detail) 机器可读 detail 码 | ✅ |
| `snippet_builder.py` | 纯函数 | 各工具 MCP 配置片段（JSON/TOML）与向导文案构建 | ✅ |
| `agent_plugin.py` | 纯函数 | Agent Plugins 1.0.0 便携 bundle（plugin.json/mcp.json/SKILL.md）模板渲染 | ✅ |

## 依赖

- `app.core.infra.ingress` — 公网 ingress 基址
- `app.config.settings` — 应用配置
- `app.config.deploy_mode` — `is_local_mode()`：LOCAL/TAURI 才允许读取本机配置文件做真实校验

## 测试契约

- Agent Plugins 官方 schema 冻结于 `tests/fixtures/agent_plugins/`（plugin.schema.json / mcp.schema.json），`test_agent_plugin_bundle.py` 用 `jsonschema.validate()` 全量校验 bundle 产物，防止模板改动破坏规范合规性。
- `test_doctor_check.py` 用临时文件逐分支覆盖 `verify_connector_config`（文件缺失/内容损坏/条目缺失/token 不匹配/env 变量令牌 token_env/Authorization 缺失 token_missing/小写 bearer scheme 仍 verified/JSON 与 TOML 两布局均 verified/无配置文件路径返回 None）。
- service/API 层 doctor 测试通过 patch `is_local_mode` 与 `verify_connector_config` 控制分支，避免测试环境绑定真实用户配置文件；`last_doctor_detail` 持久化跨实例加载断言（SANDBOX `token_valid` → 前端琥珀三态；旧状态文件缺省空串向后兼容）。
