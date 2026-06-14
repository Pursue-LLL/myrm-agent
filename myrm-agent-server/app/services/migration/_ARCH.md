# services/migration 模块架构


## 架构概述

竞品数据迁移服务层（**仅 Local WebUI / Tauri**；SaaS 沙箱不提供发现与导入）。四车道编排：指令（Agent system_prompt / 全局设置 / `.myrm/rules`）、全局记忆、技能审核、凭证 opt-in。Wizard dry-run 必须使用竞品 id 映射的 memory adapter source（禁止裸 `auto` 误路由）。OpenClaw workspace Markdown 合并进 `openclaw_memory`；多 workspace 同文件名合并。MCP/渠道在覆盖矩阵标 manual。dry-run 返回 `instruction_total_chars`、`providers_configured` 与车道 warning/critical 状态。

支持的竞品工具：Hermes、Claude Code、OpenClaw、Cursor、Codex、Windsurf、Trae、QwenPaw（共 8 种）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `competitor_discovery.py` | 核心 | 数据类定义、工具函数、discover_competitors 编排入口 | ✅ |
| `competitor_probes.py` | 核心 | 8 个 per-competitor probe 实现（Hermes/Claude/OpenClaw/Cursor/Codex/Windsurf/Trae/QwenPaw） | ✅ |
| `competitor_payload_loader.py` | 核心 | 公共 API：load_competitor_payload / build_coverage_items / extract_pending_skills | ✅ |
| `competitor_payload_loaders_impl.py` | 核心 | 基础 loaders（hermes/cursor/codex/claude/windsurf/trae）+ re-export 统一入口 | ✅ |
| `_loaders_openclaw_qwenpaw.py` | 核心 | 复杂 loaders（openclaw/qwenpaw）+ 专有 helpers | ✅ |
| `_loader_utils.py` | 辅助 | 跨 loader 模块共享工具函数（read_text/json/yaml, path_by_kind 等） | ✅ |
| `competitor_secrets_importer.py` | 辅助 | opt-in 从竞品 `.env` 导入 API Key；无 provider 槽位时创建最小 stub | ✅ |
| `competitor_model_migrator.py` | 辅助 | Hermes auxiliary model → Myrm categorical model slots 自动映射 | ✅ |
| `competitor_migration_types.py` | 核心 | 四车道迁移 DTO（instruction / memory / skill / credential） | ✅ |
| `competitor_payload_split.py` | 核心 | 将竞品 payload 拆分为 instruction 与 memory 两路 | ✅ |
| `instruction_writer.py` | 核心 | 写入 Agent.systemPrompt、personalSettings、.myrm/rules | ✅ |
| `memory_import_binding.py` | 辅助 | 全局 namespace MemoryManager 工厂（迁移事实记忆） | ✅ |
| `instruction_rollback.py` | 辅助 | 与 memory import batch 绑定的指令车道回滚 | ✅ |
| `skill_binding.py` | 辅助 | 技能审核通过后绑定 Agent profile `skills` 列表 | ✅ |

待审核列表 API（`app.api.skills.migrations`）在响应中附带 `target_agent_id` / `target_agent_name`，供前端批准前展示绑定目标。

## 模块依赖

- `app.services.memory.import_adapters` — 记忆车道 dry-run / confirm
- `app.services.memory.import_sessions` — dry-run 会话 metadata（instruction plan）
- `app.services.memory.operations.crud.import_archive` — 竞品发现 payload 编排入口
- `app.api.skills.migrations` — 技能审核队列 API
- `app.services.config.service` — 凭证车道 opt-in 写入
