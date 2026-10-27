# workspace_trust/

## 架构概述

Folder bind trust + side-channel execution control. Harness owns gate logic and run-scoped ContextVars; server owns UserConfig persistence and REST API (`/security/workspace-trust/*`).

详细设计见 [SECURITY_SYSTEM.md](../SECURITY_SYSTEM.md)（Workspace Trust 节，待补全）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.py` | Core | `WorkspaceTrustLevel`、`WorkspaceTrustManifest`（含 `pending_command_prefixes`）、`WorkspaceTrustEntry`（含用户信任时看过的 `disclosed_command_prefixes`） | ✅ |
| `manifest.py` | Core | Pre-bind disclosure builder（声明前缀减去已披露前缀得 `pending_command_prefixes`）+ `manifest_hash`（不含 pending/level，预览与决定之间保持稳定） | ✅ |
| `gate.py` | Core | Side-channel block helpers（skills/rules/MCP spawn/repo prefix match；前缀按整词匹配：`npm run test` 覆盖 `npm run test -w a`，不覆盖 `npm run testing`；复合命令一律不匹配） | ✅ |
| `errors.py` | Core | `WorkspaceTrustBlockedError` for MCP spawn and side-channel blocks | ✅ |
| `context.py` | Core | ContextVar：trust level + workspace root + repo command prefixes | ✅ |
| `protocol.py` | Core | `WorkspaceTrustLookup` protocol（server 注入；`get_level` + `get_disclosed_command_prefixes`） | ✅ |
| `provider.py` | Core | Lookup registry；`resolve_workspace_trust_level`（unknown → RESTRICTED）；`resolve_disclosed_command_prefixes`（无 lookup → 空） | ✅ |
| `runtime.py` | Core | `apply_workspace_trust_for_root` / `clear_workspace_trust_runtime`（run lifecycle）；TRUSTED 时仅让「声明 ∩ 已披露」的 repo 前缀生效，其余记 warning 并保持惰性 | ✅ |
| `repo_policy.py` | Core | `.myrm/config.toml` command prefix loader；`partition_command_prefixes`（声明前缀按用户是否看过分为 approved / pending） | ✅ |
| `__init__.py` | Package | Public exports | ✅ |

## 边界

- 位于 `agent/security/workspace_trust/`，**非** `toolkits/`，**非** meta-tool。
- Control plane 层：**零改动**。
- 声明前缀的信任边界：沙箱内 agent 能写工作区的 `.myrm/config.toml`，所以仓库声明的命令前缀只在用户于信任弹窗中看过它之后才生效；文件夹信任本身不再自动覆盖之后新增的前缀。
