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
| `test_arch_no_placeholder.py` | 产品树 `_ARCH.md` 禁止「见源码」等占位短语 |
| `test_oss_scripts_arch.py` | `scripts/` 子树（ci/dev/lib）必须有 `_ARCH.md` |
| `test_integrations_hardware_routes.py` | `/api/v1/integrations/hardware/*` 路由已注册（防 prefix 回归） |
| `test_cookbook_specs_asset.py` | `assets/cookbook_specs.json` bundled 结构校验 |
| `data/server_harness_import_baseline.txt` | harness import 允许 baseline |
| `data/fractal_header_baseline.txt` | `check_fractal_docs --strict-headers` 已知缺 header 的 app 相对路径 |

## 依赖

- `myrm-agent-server/pyproject.toml` — harness 版本 pin
- `myrm-agent-server/uv.lock` — OSS `main` 须 PyPI registry pin；vortexai 联调可用 editable（勿提交到 OSS `main`）

## 运行

- 本地 / vortexai：`bash myrm-agent-server/scripts/ci/run_architecture_gates.sh`（`check_fractal_docs.py` + pytest；旁路 `myrm-agent-harness/`）
- CI：`myrm-agent/.github/workflows/server-architecture.yml`（无 PyPI 且无 checkout harness 时失败闭合）
