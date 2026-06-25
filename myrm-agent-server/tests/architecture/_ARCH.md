# tests/architecture/ 模块架构

## 架构概述

Server 层架构约束测试：禁止新增 harness 深导入、禁止 `uv.lock` editable harness pin、禁止跟踪 markdown 链到私有开发壳 `temp-docs/`。

## 文件清单

| 文件 | 职责 |
|------|------|
| `test_sse_event_type_parity.py` | harness `AgentEventType` ⊆ 前端 `knownSseEventTypes` 清单 |
| `../fixtures/frontend_sse_event_types.json` | 由 frontend `scripts/export-known-sse-event-types.ts` 生成 |
| `test_server_harness_imports.py` | 相对 baseline 禁止新增 server→harness 内部 import |
| `test_uv_lock_harness_registry.py` | 主 wheel + 平台 core 均上 PyPI 后，`uv.lock` 须 registry pin（否则 skip，允许 monorepo editable） |
| `test_no_user_id.py` | 单机 server 禁止多租户 user_id 泄漏 |
| `test_no_temp_docs_links.py` | 跟踪的 `*.md` 禁止 `temp-docs/` 相对路径（私有开发壳） |
| `test_arch_no_placeholder.py` | 产品树 `_ARCH.md` 禁止「见源码」等占位短语（含 `myrm-agent-extension/`） |
| `test_oss_scripts_arch.py` | `scripts/` 子树（ci/dev/lib）必须有 `_ARCH.md` |
| `test_sync_arch_guard.py` | `sync_arch_file_tables.py` 不得覆盖已人工维护的 `_ARCH.md`（混合 stub/✅ 或多余章节） |
| `test_no_app_main_in_tests.py` | `tests/**` 禁止 AST 级 `import app.main`（须用 `build_minimal_app`） |
| `test_integrations_hardware_routes.py` | `/api/v1/integrations/hardware/*` 路由已注册（防 prefix 回归） |
| `test_api_services_vocabulary.py` | `app/api/` 与 `app/services/` 顶域分区 + 别名表与 `CONTRIBUTING.md` 同步 |
| `test_calendar_schema_retired.py` | 磁盘无 calendar ORM/API；`migrations.py` 尾部 DROP calendar_events 表/索引 |
| `test_migration_source_closure.py` | Wizard 封闭 4 源：probe 导出 ≡ `supported_source_ids()` ≡ loader 注册 |
| `test_cookbook_specs_asset.py` | `assets/cookbook_specs.json` bundled 结构校验 |
| `data/server_harness_import_baseline.txt` | harness import 允许 baseline |
| `data/fractal_header_baseline.txt` | `check_fractal_docs --strict-headers` 已知缺 header 的 app 相对路径 |
| `../../scripts/ci/file_line_budget_baseline.txt` | `check_file_line_budget.py` grandfather 超标模块列表 |

## 依赖

- `myrm-agent-server/pyproject.toml` — harness 版本 pin
- `myrm-agent-server/uv.lock` — OSS `main` 须 PyPI registry pin；本地 editable harness 仅用于开发联调（勿提交到 OSS `main`）

## 运行

- 本地：`bash myrm-agent-server/scripts/ci/run_architecture_gates.sh`（fractal + `--no-stub` + line budget + architecture pytest）
- CI：`myrm-agent/.github/workflows/server-architecture.yml`（无 PyPI 且无 checkout harness 时失败闭合）
