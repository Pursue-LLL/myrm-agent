# services/migration 模块架构

## 架构概述

外部 AI 助手数据迁移服务层（三部署均等：Local/Tauri 使用文件系统扫描，Cloud/SaaS 通过 ZIP 上传）。五车道编排：指令（Agent system_prompt / 全局设置 / `.myrm/rules`）、全局记忆、技能审核、凭证 opt-in、**MCP 配置迁移**、**Hermes Cron 定时任务（paused 导入 + batch rollback）**。Wizard dry-run 必须使用 source id 映射的 memory adapter（禁止裸 `auto` 误路由）。OpenClaw workspace Markdown 合并进 `openclaw_memory`；多 workspace 同文件名合并。MCP 配置从竞品 payload 自动提取并转换为 MCPServerConfig 格式，默认 `enabled: false`，用户在前端审核后手动启用；当竞品显式声明 `supports_parallel_tool_calls: false`（或 `supportsParallelToolCalls: false`）时，会映射为 `hostSerial: true` 保留串行策略语义；`transport=http` 会归一化为 `streamable_http`；若提供 `keepalive_interval` / `keepaliveInterval`，仅在 remote transport 且 `>=5s` 时透传为 `keepaliveInterval` 供长连接保活，`stdio` 或低于 5 秒的值会被忽略并在 preview 中标记解释。渠道在覆盖矩阵标 manual。迁移来源元数据由 `source_manifest.py` 单一真源维护（display name / import source / discover mode / deep-link capability），API 明确下发 `source_manifest_authoritative` 覆盖语义，前端据此决定是否替换本地默认映射；当 payload 未完整覆盖 SSOT source ids 时会自动降级 `source_manifest_authoritative=false`。

### 支持范围策略（封闭集合）

**Wizard 自动发现的来源（本地 filesystem scan）固定为 5 种：**

| id | 产品名 | 发现方式 |
|----|--------|----------|
| `hermes` | Hermes | 本地 scan |
| `openclaw` | OpenClaw | 本地 scan |
| `claude` | Claude Code | 本地 scan |
| `codex` | Codex | 本地 scan |
| `pi` | Pi | 本地 scan |

**ZIP upload 检测的来源（Cloud/SaaS 与 Local 均可）：**

| id | 产品名 | 发现方式 |
|----|--------|----------|
| `chatgpt` | ChatGPT | ZIP upload 内检测 conversations.json |
| `gbrain` | gbrain | ZIP upload 内检测 ≥3 个含 YAML frontmatter `type:` 字段的 .md 文件 |

**政策**：不添加 Cowork、Cursor、Windsurf、Trae、QwenPaw 或其他工具的 Wizard 扫描/导入。Memory Center 手动导入（如 `cursor_rules`、`mem0`、归档 JSON）与 Wizard discover **解耦**，不受此政策限制。ChatGPT 属于 upload-only 类型，不扩展 filesystem probe。

新增 probe/loader 须修改本 `_ARCH.md` 并获产品确认；默认拒绝。

**Architecture 守门**：`tests/architecture/test_migration_source_closure.py` 强制 probe 模块、`supported_source_ids()`、loader 注册三处同步。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `source/`（子包） | 核心 | 迁移源处理子域：发现、SSOT 清单、探针、payload 加载与拆分、迁移 DTO、凭证导入、模型迁移。9 个 `source_*` 模块聚合于此，`source/__init__.py` 为聚合门面统一 re-export | ✅ |
| `hermes/`（子包） | 核心 | Hermes 迁移子域：cron 迁移（jobs.json → Myrm CronJob 映射 + dry-run plan + confirm 写入 CronManager 默认 paused + batch rollback）与 MoA 迁移（`moa.presets` → 目标 Agent `moa_overlay`）。3 个 `hermes_*` 模块聚合于此，`hermes/__init__.py` 为聚合门面统一 re-export | ✅ |
| `_loaders_openclaw.py` | 核心 | OpenClaw 复杂 loader（多 workspace、sessions、skills） | ✅ |
| `_loaders_pi.py` | 核心 | Pi loader（AGENTS.md、settings.json、auth.json、sessions/*.jsonl、skills/） | ✅ |
| `_loader_utils.py` | 辅助 | 跨 loader 共享工具函数（含 load_usage_sidecar 读取 Hermes .usage.json） | ✅ |
| `source_secrets_importer.py` | 辅助 | opt-in 从竞品 `.env` 导入 API Key | ✅ |
| `source_model_migrator.py` | 辅助 | 竞品模型配置 → Myrm 模型设置（Hermes auxiliary slots + Smart Routing economy 推断；仅 migrated_slots 非空时启用 routing），由 Wizard confirm 调用 | ✅ |
| `instruction_writer.py` | 核心 | 写入 Agent.systemPrompt、personalSettings、`.myrm/rules` | ✅ |
| `memory_import_binding.py` | 辅助 | 全局 namespace MemoryManager 工厂 | ✅ |
| `instruction_rollback.py` | 辅助 | 与 memory import batch 绑定的指令车道回滚 | ✅ |
| `skill_binding.py` | 辅助 | 技能审核通过后绑定 Agent profile | ✅ |
| `mcp_config_converter.py` | 核心 | 竞品 MCP 配置 → MCPMigrationItem → config dict / preview；无状态转换器；并发策略映射（`supports_parallel_*` ↔ `hostSerial`）；transport 别名收敛（`http` → `streamable_http`）；可选保活间隔映射（`keepalive*` → `keepaliveInterval`；仅 remote transport 生效，`stdio` 或低于 5 秒时标记 `keepaliveIntervalIgnored` 供前端解释） | ✅ |
| `workspace_bind_candidates.py` | 辅助 | OpenClaw migration → project workspace bind 候选路径 + Obsidian/md fingerprint；dry-run/confirm 响应与 session metadata SSOT | ✅ |

### source/ 子包内部结构

```
source/
├── __init__.py               # 聚合门面，统一 re-export 9 个模块公共符号
├── source_discovery.py       # 数据类 + discover_external_sources 编排入口
├── source_manifest.py        # 迁移来源 SSOT（display name / import map / discover / deep-link）
├── source_probes.py          # 5 源 filesystem probe（hermes/claude/openclaw/codex/pi）
├── source_payload_loader.py  # 公共 API：load_source_payload / build_coverage_items / extract_pending_skills
├── source_payload_loaders_impl.py # 基础 loaders（hermes/codex/claude/chatgpt/gbrain）+ re-export openclaw/pi
├── source_payload_split.py   # payload 拆分为 instruction 与 memory 两路
├── source_migration_types.py # 四车道迁移 DTO
├── source_secrets_importer.py # opt-in 从竞品 .env 导入 API Key
└── source_model_migrator.py  # 竞品模型配置 → Myrm 模型设置
```

## 模块依赖

- `app.services.memory.imports.import_adapters` — 记忆车道 dry-run / confirm
- `app.services.memory.imports.import_sessions` — dry-run 会话 metadata（instruction plan）
- `app.services.memory.operations.crud.import_archive` — 竞品发现 payload 编排入口
- `app.api.skills.migrations` — 技能审核队列 API
- `app.services.config.service` — 凭证车道 opt-in 写入
