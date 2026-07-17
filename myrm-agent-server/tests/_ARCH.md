# tests 模块架构

pytest 测试套件根目录。单元/集成/API/E2E 测试按域分子目录；[T] 业务密钥仅通过结构化 fixture 加载，不进入 server 运行时。

---

## 文件清单

| 路径 | 地位 | 职责 |
|------|------|------|
| `conftest.py` | 核心 | 进程级 `.env` + [T] secrets bootstrap、隔离 workspace、`test_secrets` session fixture、integration/e2e 路径每测后 `reset_global_browser_pool_for_tests()`、session 结束 `reset_database_engine()` + `shutdown_cached_memory_managers()`、浏览器进程树 cleanup（`tests/support/browser_process_cleanup`） |
| `support/browser_process_cleanup.py` | 辅助 | pytest 进程树内 browser 自动化子进程 teardown |
| `support/test_browser_process_cleanup.py` | 单元 | browser_process_cleanup 单测（100% 覆盖） |
| `support/test_secrets.py` | 核心 | [T] `.env.test` 结构化加载（`TestSecrets`、`load_test_secrets`、`resolve_test_env`） |
| `support/minimal_app.py` | 核心 | `build_minimal_app(preset=...)` 按需挂载 API 路由；禁止测试 import `app.main` |
| `support/feature_flags.py` | 辅助 | `seed_voice_interaction_flags()`，供 `tests/api/voice`、`tests/api/stt` conftest autouse |
| `support/bash_compressor_e2e.py` | 辅助 | bash compressor live/API E2E 共享 helper（模型 probe、workspace 压缩回放） |
| `api/agent/utils.py` | 辅助 | Agent 测试共享工具（模型/搜索配置组装） |
| `e2e/conftest.py` | 辅助 | E2E ephemeral server fixture（API 级 e2e，不启动前端） |
| `benchmarks/bench_mcp_ptc_vs_direct.py` | 基准 | MCP PTC vs 直连 token/延迟对比；凭据仅来自 `.env.test` |
| `fixtures/cp_proxy_signature_contract.json` | 辅助 | 控制服务反向代理 HMAC 契约向量（server 侧自包含） |
| `../scripts/dev/run_tests_low_memory.sh` | 辅助 | 本地低内存 pytest 入口（`-n0`，可选 `PYTEST_XDIST_WORKERS=N`） |
| `../scripts/dev/profile_test_memory.py` | 辅助 | 按 test 文件采样 peak RSS，定位高内存用例 |
| `services/migration/_ARCH.md` | 模块 | 迁移业务层测试清单（四源 discover/load/e2e） |
| `services/hosting/` | 模块 | 多 target artifact 发布 API 与 provider 单测 |
| `architecture/_ARCH.md` | 模块 | 架构约束测试（含 migration 源闭包） |
| `remote_access/` | 模块 | 远程访问 trust_zone / pairing / E2EE / mobile_gate / host_allowlist 单测（16 文件） |

---

## [T] 测试密钥约定

1. 开发者复制 `myrm-agent-server/.env.test.example` → `.env.test`（gitignored）
2. `tests/conftest.py` 调用 `apply_test_secrets_to_environ()` 供 legacy `skipif(os.getenv(...))` 兼容
3. 新测试优先使用 `test_secrets` fixture 或 `resolve_test_env()`，禁止在源码中硬编码密钥
4. 权威变量索引：`.env.example`（[P/O]）、`.env.sandbox.example`（[S]）、`.env.test.example`（[T]）

---

## 测试分层（默认 `pytest`）

- 默认 `addopts`：`-m 'not e2e and not chrome_e2e and not performance'`（跳过 e2e、Chrome MCP UI E2E 与 benchmark/performance）
- **低内存推荐（本地 / CI 同款）**：`scripts/dev/run_tests_low_memory.sh` 或 monorepo **`./myrm test -n0`**
- 单元 + API 集成：monorepo **`./myrm test -n0`**（单 worker；实测 `build_minimal_app(chats)` ~118MB，`app.main` ~439MB）
- E2E（真实 LLM API，无 Chrome）：monorepo **`./myrm test -m e2e`**（如 `tests/api/agent/test_render_ui_agent_stream_e2e.py`）
- **Chrome MCP UI E2E（14 项）**：`RUN_E2E_TESTS=1 ./myrm test -m chrome_e2e -n0`（须 `./myrm ready --chrome`；SHPOIB 私 Backend；见 `scripts/dev/CHROME_MCP_E2E.md`）
- `tests/integration/test_render_ui_sse_wiring.py`：render_ui 确定性集成（20 场景：run_bind、fail-closed、data_update、collector 链、幂等）
- 并行（内存充足时）：`PYTEST_XDIST_WORKERS=4 scripts/dev/run_tests_low_memory.sh`；避免 `-n auto`（多 worker RSS 叠加，`-n auto` 在 8 核上可达数 GB）
- 定位高内存文件：`uv run python scripts/dev/profile_test_memory.py tests/api/agent --top 20`
- WebUI E2E：MCP **chrome-devtools** + Myrm E2E Chrome `:9333`（`./myrm ready --chrome`）；marker **`chrome_e2e`**（`lane=READ|LIVE_AGENT`）；禁止 `@playwright/test`。正式入口 **`./myrm test -m chrome_e2e`**；`tests/e2e/test_*_chrome_e2e.py`（含 Goal、execution_cache、edge_tts、parallel_tabs READ lane 等）；READ 只读测例不占 LIVE_AGENT cap（`resolve_e2e_session_lane.py`）
- CI 默认套件：`scripts/ci/run_default_tests.sh`（`-m 'not e2e and not performance' -n0`，workflow `server-unit-tests.yml`）
- `tests/api/skills/test_drafts_seed_mock.py`：seed-mock HTTP 单测（含 `agent_id` 查询参数，默认套件执行）
- `tests/api/approvals/test_list_pending_growth_filter.py`：`GET /approvals` 排除后台 growth、保留 inline `thread_id` skill_draft
- `tests/api/skills/conftest.py`：minimal app 含 drafts/curator/sync/evolution/skill-growth 路由
- `tests/api/integrations/test_llm_speed_test.py`：`POST /api/v1/integrations/llm/speed-test`
- `tests/api/notifications/conftest.py`：in-memory DB + loopback auth（通知 API 集成测）
- `tests/api/config/test_readiness_e2e.py`、`tests/api/security/test_generate_policy_e2e.py`：`@pytest.mark.e2e`（默认套件不收集）

## 依赖

- `tests/conftest.py` → `tests/support/test_secrets.py`（**唯一** [T] 加载入口）
- 新 API/集成测优先 `from tests.support.minimal_app import build_minimal_app` + `preset_for_test_path()`，禁止 `from app.main import app`
- `tests/conftest.py` → integration/e2e/lifecycle 路径 autouse `reset_global_browser_pool_for_tests()`（防 Chromium 跨测累积）；sessionfinish 释放 DB engine 与 `_memory_manager_cache`
- `tests/unit/test_system_storage.py`：系统存储 API 单元测（**禁止**在 `tests/unit/` 下创建 `api/` 子包，会与 `tests/api/` 在 `import_mode=importlib` 下冲突）
- `app/startup/env_loader.py` **不**读取 `.env.test`
