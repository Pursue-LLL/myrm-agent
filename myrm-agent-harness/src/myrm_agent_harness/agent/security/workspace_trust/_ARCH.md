# workspace_trust/

## 架构概述

Folder bind trust + side-channel execution control. Harness owns gate logic and run-scoped ContextVars; server owns UserConfig persistence and REST API (`/security/workspace-trust/*`).

详细设计见 [SECURITY_SYSTEM.md](../SECURITY_SYSTEM.md)（Workspace Trust 节，待补全）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.py` | Core | `WorkspaceTrustLevel`、`WorkspaceTrustManifest`（含 `pending_command_prefixes`）、`WorkspaceTrustEntry`（含用户信任时看过的 `disclosed_command_prefixes`） | ✅ |
| `manifest.py` | Core | Pre-bind disclosure builder（声明前缀减去已披露前缀得 `pending_command_prefixes`）+ `manifest_hash`（不含 pending/level，预览与决定之间保持稳定）。披露发生在用户决定之前，所读文件的大小与种类由仓库决定：MCP 配置经 `core.security.path.read_text_bounded` 读取（上限 `MAX_WORKSPACE_CONFIG_CHARS`），读不完整的配置按一个 server 计；workspace skills 的 SKILL.md 同样走有界读取（FIFO、设备、超限一律跳过） | ✅ |
| `gate.py` | Core | Side-channel block helpers（skills/rules/MCP spawn/repo prefix match；前缀按整词匹配：`npm run test` 覆盖 `npm run test -w a`，不覆盖 `npm run testing`；复合命令一律不匹配） | ✅ |
| `errors.py` | Core | `WorkspaceTrustBlockedError` for MCP spawn and side-channel blocks | ✅ |
| `context.py` | Core | ContextVar：trust level + workspace root + repo command prefixes；`workspace_side_channels_blocked()` 是仓库本地侧信道（顶层规则注入、子目录规则发现）共用的闸门判断，无信任级别按受限处理 | ✅ |
| `protocol.py` | Core | `WorkspaceTrustLookup` protocol（server 注入；`get_level` + `get_disclosed_command_prefixes`） | ✅ |
| `provider.py` | Core | Lookup registry；`resolve_workspace_trust_level`（unknown → RESTRICTED）；`resolve_disclosed_command_prefixes`（无 lookup → 空） | ✅ |
| `runtime.py` | Core | `apply_workspace_trust_for_root` / `clear_workspace_trust_runtime`（run lifecycle）；TRUSTED 时仅让「声明 ∩ 已披露」的 repo 前缀生效，其余记 warning 并保持惰性 | ✅ |
| `repo_policy.py` | Core | `.myrm/config.toml` command prefix loader（经 `read_text_bounded` 读取，上限 `MAX_WORKSPACE_CONFIG_CHARS` = 1,048,576 字符，超限或非常规文件记 warning 并视为未声明前缀）；`partition_command_prefixes`（声明前缀按用户是否看过分为 approved / pending） | ✅ |
| `__init__.py` | Package | Public exports | ✅ |

## 边界

- 位于 `agent/security/workspace_trust/`，**非** `toolkits/`，**非** meta-tool。
- Control plane 层：**零改动**。
- 信任前读取的边界：FolderGate 披露在用户做出决定之前就读取工作区内的 SKILL.md、规则文件、`mcp.json`、`.myrm/config.toml`。这些文件的大小与种类由仓库作者决定（指向 `/dev/zero` 的符号链接、FIFO、稀疏的多 GB 文件），所以全部经 `core.security.path.read_text_bounded`：最多解码 `max_chars + 1` 个字符，非常规文件不读不等待。披露本身对扫描失败降级为零计数，不阻塞弹窗。
- 声明前缀的信任边界：沙箱内 agent 能写工作区的 `.myrm/config.toml`，所以仓库声明的命令前缀只在用户于信任弹窗中看过它之后才生效；文件夹信任只覆盖用户看过的前缀，之后新增的前缀不会自动生效。
