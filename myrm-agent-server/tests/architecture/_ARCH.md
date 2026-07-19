# tests/architecture/ 模块架构

## 架构概述

Server 层架构约束测试：禁止新增 harness 深导入、禁止 `uv.lock` editable harness pin、禁止跟踪 markdown 链到私有开发壳 `temp-docs/`。

## 文件清单

| 文件 | 职责 |
|------|------|
| `test_sse_event_type_parity.py` | harness `AgentEventType` ⊆ 前端 `knownSseEventTypes` 清单 |
| `test_memory_injection_contract_parity.py` | 前端 `MemoryBriefStatus(source)/MemoryBriefInjectionStatus` union 与 server+harness 状态契约严格同构 |
| `test_memory_brief_prometheus_rules_contract.py` | memory brief 告警规则契约（flush HTTP attempts-based ratio + strict dedup reject ratio/burst 关键片段；直接跑 pytest 时本地无 promtool 可 skip；`scripts/ci/run_architecture_gates.sh` 与 CI 均强制 promtool `check rules`） |
| `test_memory_brief_telemetry_layout.py` | memory brief CP 遥测须位于 `app/services/agent/memory_brief_telemetry/` 子包，禁止根目录 legacy 平铺文件复活 |
| `test_builtin_specs_layout.py` | 预置智能体规格须位于 `app/services/agent/builtin_specs/` 子包，禁止根目录 legacy 平铺文件复活 |
| `test_memory_guardian_guard_telemetry_layout.py` | memory guardian guard CP 遥测须位于 `app/services/agent/memory_guardian_guard_telemetry/` 子包，禁止根目录 legacy 平铺文件复活 |
| `test_marketplace_layout.py` | Agent Marketplace 导入/导出须位于 `app/services/agent/marketplace/` 子包，禁止根目录 legacy 平铺文件复活 |
| `test_app_package_init_layout.py` | `app/**` 含 `.py` 的目录须声明 `__init__.py`（禁止隐式 namespace 包） |
| `test_conversation_recall_layout.py` | Conversation Recall 仓储须位于 `app/database/repositories/conversation_recall/` 子包，禁止 repositories 根 legacy 平铺文件复活 |
| `test_e2ee_layout.py` | Mobile remote E2EE 须位于 `app/remote_access/e2ee/` 子包，禁止 remote_access 根 legacy 平铺文件复活 |
| `test_builtin_agent_i18n_parity.py` | 前端 `builtin-agent-i18n-data.ts` 的 key 集合须与 server `_BUILTIN_AGENTS` id 严格同构 |
| `../fixtures/frontend_sse_event_types.json` | 由 frontend `scripts/export-known-sse-event-types.ts` 生成 |
| `test_server_harness_imports.py` | 相对 baseline 禁止新增 server→harness 内部 import；并禁止 import 含 ``._`` 的 harness 私有模块路径 |
| `test_dev_pid_path_ssot.py` | `scripts/**` 禁止读取子目录 `.myrm-dev-*` pid（cleanup rm 豁免） |
| `test_uv_lock_harness_registry.py` | 主 wheel + 平台 core 均上 PyPI 后，`uv.lock` 须 registry pin（否则 skip，允许 monorepo editable） |
| `test_no_user_id.py` | 单机 server 禁止多租户 user_id 泄漏 |
| `test_no_temp_docs_links.py` | 跟踪的 `*.md` 禁止 `temp-docs/` 相对路径（私有开发壳） |
| `test_arch_no_placeholder.py` | 产品树 `_ARCH.md` 禁止「见源码」等占位短语（含 `myrm-agent-extension/`） |
| `test_server_scripts_arch.py` | `myrm-agent-server/scripts/**` 子树必须有 `_ARCH.md` |
| `test_sync_arch_guard.py` | `sync_arch_file_tables.py` 不得覆盖已人工维护的 `_ARCH.md`（混合 stub/✅ 或多余章节） |
| `test_no_app_main_in_tests.py` | `tests/**` 禁止 AST 级 `import app.main`（须用 `build_minimal_app`） |
| `test_unit_test_layout.py` | 禁止 `tests/unit/**/api/`（与 `tests/api/` importlib 包名冲突） |
| `test_integrations_hardware_routes.py` | `/api/v1/integrations/hardware/*` 路由已注册（防 prefix 回归） |
| `test_api_services_vocabulary.py` | `app/api/` 与 `app/services/` 顶域分区 + 别名表与 `CONTRIBUTING.md` 同步 |
| `test_calendar_schema_retired.py` | 磁盘无 calendar ORM/API；`migrations.py` 尾部 DROP calendar_events 表/索引 |
| `test_migration_source_closure.py` | Wizard 封闭 4 源：probe 导出 ≡ `supported_source_ids()` ≡ loader 注册 |
| `test_cookbook_specs_asset.py` | `assets/cookbook_specs.json` bundled 结构校验 |
| `data/server_harness_import_baseline.txt` | harness import 允许 baseline |
| `test_no_core_services_api_imports.py` | `app/{core,services,lifecycle}/` 禁止 import `app.api` |
| `test_telegram_channel_mixin_mro.py` | `TelegramChannel._pre_emit_hook` 必须来自 hooks mixin；inbound 不得定义同名方法 |
| `data/server_api_import_baseline.txt` | 上述门禁 baseline（须保持为空） |
| `../../scripts/ci/file_line_budget_baseline.txt` | `check_file_line_budget.py` grandfather 超标模块列表 |

## 依赖

- `myrm-agent-server/pyproject.toml` — harness 版本 pin
- `myrm-agent-server/uv.lock` — OSS `main` 须 PyPI registry pin；本地 editable harness 仅用于开发联调（勿提交到 OSS `main`）

## 运行

- 本地：`bash myrm-agent-server/scripts/ci/run_architecture_gates.sh`（fractal + `--no-stub` + line budget + `promtool check rules` + architecture pytest）
- CI：`myrm-agent/.github/workflows/server-architecture.yml`（无 PyPI 且无 checkout harness 时失败闭合）
