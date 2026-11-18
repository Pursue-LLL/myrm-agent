# services/migration/source 子包架构

## 架构概述

外部数据迁移的**迁移源处理子域**，聚合 `source_*` 模块：来源发现、SSOT 清单、探针、payload 加载与拆分、迁移 DTO、凭证导入、模型迁移。`__init__.py` 为聚合门面统一 re-export 全部公共符号，`app/services/migration/_ARCH.md` 的「文件清单」以本子包为整体条目引用。

封闭集合策略（wizard 自动发现 6 源：hermes/claude/openclaw/codex/pi/plur；ZIP upload 通道：chatgpt/gbrain 与 plur 双模式）与 probe/loader 变更守门规则由父级 `_ARCH.md` 定义；`tests/architecture/test_migration_source_closure.py` 强制 probe 模块、manifest 本地扫描 id 集合与 loader 注册三处同步。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合 re-export 全部公共符号，收敛为单入口 | ✅ |
| `source_discovery.py` | 核心 | DiscoveredFile / ExternalSource / DiscoveryResult 数据类 + discover_external_sources 编排入口；`ExternalSource.has_api_keys` 表示发现了任何 key，`has_importable_keys` 只表示 `.env` 里有 opt-in 导入能带走的 key（auth.json 与 Pi 的 key 不算） | ✅ |
| `source_manifest.py` | SSOT | 迁移来源清单（display name / import map / discover mode / deep-link capability）与 authoritative 判定 | ✅ |
| `source_probes.py` | 核心 | 6 源本地 filesystem probe（hermes/claude/openclaw/codex/pi/plur；claude 含 `projects/*/memory` 自动记忆与 `autoMemoryDirectory`，codex 含 `memories/MEMORY.md`） | ✅ |
| `source_payload_loader.py` | 核心 | 公共 API：load_source_payload / build_coverage_items / extract_pending_skills；上传临时目录策略（前缀常量、TTL 清扫、归档包含性校验） | ✅ |
| `source_payload_loaders_impl.py` | 核心 | 基础 loaders（hermes/codex/chatgpt/gbrain）+ re-export 三个来源车道（`_loaders_claude.py` / `_loaders_openclaw.py` / `_loaders_pi.py`）；Hermes 的 `auth.json` 只贡献 provider 名（`KEY_FROM_AUTH`），key 值与登录态不进 payload（payload 会交给预览会话与记忆适配器） | ✅ |
| `source_payload_split.py` | 核心 | payload 拆分为 instruction 与 memory 两路（build_instruction_plan / extract_memory_payload）；`has_api_keys` / `has_importable_keys` 按 key 名的来源标记判断 payload 里有没有 key、有没有 opt-in 导入能带走的 key；设置文件（Cursor / Codex / Claude / Pi）以去掉凭证的 JSON 进入全局补充（`env` / `headers` 只留变量名，含凭证的字符串整体替换为 `[redacted]`，判断复用 harness 的脱敏域），因为补充会随审阅会话落库、并在 confirm 写进全局指令 | ✅ |
| `source_migration_types.py` | 核心 | 四车道迁移 DTO（MigrationLanePreview / SourceInstructionPlan / MigrationWizardOptions 等）；凭证车道有 key 且 provider 就绪时，能 opt-in 导入则提示可选导入，否则提示到 provider 设置手动填写；`MIGRATION_CONFIG_DEVICE_ID` 是迁移各车道改配置行时审计日志记录的写入者 | ✅ |
| `source_secrets_importer.py` | 辅助 | opt-in 从竞品 `.env` 导入 API Key（仅本机/Tauri）：key 的读取与变量清单来自上一级 `env_secrets.py`（迁移预览、payload 的 key 名与导入共用），本模块只负责写入 provider 配置；用户已有的 provider 行（id 或 routingProfile 匹配）直接填 key，没有行时只为单凭 key 即可用的 provider 新建（含 Vercel AI Gateway），多端点 provider 不新建而记为 `needs_endpoint`，没有对应 provider 的 key 变量记为 `unsupported`；结果只含变量名，不含值 | ✅ |
| `source_model_migrator.py` | 辅助 | 竞品模型配置 → Myrm 模型设置（Hermes auxiliary slots + Smart Routing economy 推断；OpenClaw 默认模型）；`extract_hermes_auxiliary_config` / `extract_openclaw_default_model_config` 只取迁移实际读取的字段（auxiliary 的 provider + model、`agents.defaults` 的 model + models），预览会话里 auxiliary 与默认模型只存这些，配置块里同级的 key 不进会话；写入以 `MIGRATION_CONFIG_DEVICE_ID` 记审计，providers 行因密钥丢失而解不开时不写（写进去会毁掉用户仍可恢复的密文） | ✅ |

## 模块依赖

- `app.services.memory.imports.import_adapters` — 记忆车道 dry-run / confirm
- `app.services.memory.imports.import_sessions` — dry-run 会话 metadata（instruction plan）
- `app.services.memory.operations.crud.import_archive` — 竞品发现 payload 编排入口
- `app.services.config.service` — 凭证车道 opt-in 写入
