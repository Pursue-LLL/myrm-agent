# services/migration 模块架构

## 架构概述

外部 AI 助手数据迁移服务层（**仅 Local WebUI / Tauri**；SaaS 沙箱不提供发现与导入）。四车道编排：指令（Agent system_prompt / 全局设置 / `.myrm/rules`）、全局记忆、技能审核、凭证 opt-in。Wizard dry-run 必须使用 source id 映射的 memory adapter（禁止裸 `auto` 误路由）。OpenClaw workspace Markdown 合并进 `openclaw_memory`；多 workspace 同文件名合并。MCP/渠道在覆盖矩阵标 manual。

### 支持范围策略（封闭集合）

**Wizard 自动发现并导入的来源固定为 4 种，且不再扩展：**

| id | 产品名 |
|----|--------|
| `hermes` | Hermes |
| `openclaw` | OpenClaw |
| `claude` | Claude Code |
| `codex` | Codex |

**政策**：不添加 Cowork、Cursor、Windsurf、Trae、QwenPaw 或其他工具的 Wizard 扫描/导入。Memory Center 手动导入（如 `cursor_rules`、`mem0`、归档 JSON）与 Wizard discover **解耦**，不受此政策限制。

新增 probe/loader 须修改本 `_ARCH.md` 并获产品确认；默认拒绝。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `competitor_discovery.py` | 核心 | 数据类定义、工具函数、discover_competitors 编排入口 | ✅ |
| `competitor_probes.py` | 核心 | 4 源 filesystem probe（hermes/claude/openclaw/codex） | ✅ |
| `competitor_payload_loader.py` | 核心 | 公共 API：load_competitor_payload / build_coverage_items / extract_pending_skills / supported_competitor_ids | ✅ |
| `competitor_payload_loaders_impl.py` | 核心 | 基础 loaders（hermes/codex/claude）+ re-export openclaw | ✅ |
| `_loaders_openclaw.py` | 核心 | OpenClaw 复杂 loader（多 workspace、sessions、skills） | ✅ |
| `_loader_utils.py` | 辅助 | 跨 loader 共享工具函数 | ✅ |
| `competitor_secrets_importer.py` | 辅助 | opt-in 从竞品 `.env` 导入 API Key | ✅ |
| `competitor_model_migrator.py` | 辅助 | Hermes auxiliary model → Myrm 模型槽（与 Wizard 数据迁移正交） | ✅ |
| `competitor_migration_types.py` | 核心 | 四车道迁移 DTO | ✅ |
| `competitor_payload_split.py` | 核心 | payload 拆分为 instruction 与 memory 两路 | ✅ |
| `instruction_writer.py` | 核心 | 写入 Agent.systemPrompt、personalSettings、`.myrm/rules` | ✅ |
| `memory_import_binding.py` | 辅助 | 全局 namespace MemoryManager 工厂 | ✅ |
| `instruction_rollback.py` | 辅助 | 与 memory import batch 绑定的指令车道回滚 | ✅ |
| `skill_binding.py` | 辅助 | 技能审核通过后绑定 Agent profile | ✅ |

## 模块依赖

- `app.services.memory.import_adapters` — 记忆车道 dry-run / confirm
- `app.services.memory.import_sessions` — dry-run 会话 metadata（instruction plan）
- `app.services.memory.operations.crud.import_archive` — 竞品发现 payload 编排入口
- `app.api.skills.migrations` — 技能审核队列 API
- `app.services.config.service` — 凭证车道 opt-in 写入
