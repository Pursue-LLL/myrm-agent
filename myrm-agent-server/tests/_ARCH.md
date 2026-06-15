# tests 模块架构

pytest 测试套件根目录。单元/集成/API/E2E 测试按域分子目录；[T] 业务密钥仅通过结构化 fixture 加载，不进入 server 运行时。

---

## 文件清单

| 路径 | 地位 | 职责 |
|------|------|------|
| `conftest.py` | 核心 | 进程级 `.env` + [T] secrets bootstrap、隔离 workspace、`test_secrets` session fixture、每测后 `reset_global_browser_pool_for_tests()` |
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
| `services/deploy/_ARCH.md` | 模块 | 部署打包业务层测试清单 |
| `architecture/_ARCH.md` | 模块 | 架构约束测试（含 migration 源闭包） |

---

## [T] 测试密钥约定

1. 开发者复制 `myrm-agent-server/.env.test.example` → `.env.test`（gitignored）
2. `tests/conftest.py` 调用 `apply_test_secrets_to_environ()` 供 legacy `skipif(os.getenv(...))` 兼容
3. 新测试优先使用 `test_secrets` fixture 或 `resolve_test_env()`，禁止在源码中硬编码密钥
4. 权威变量索引：`.env.example`（[P/O]）、`.env.sandbox.example`（[S]）、`.env.test.example`（[T]）

---

## 测试分层（默认 `pytest`）

- 默认 `addopts`：`-m 'not e2e'`（跳过需真实 LLM / 长链路 e2e）
- **低内存推荐（本地 / CI 同款）**：`scripts/dev/run_tests_low_memory.sh` 或 `uv run pytest -n0`
- 单元 + API 集成：`uv run pytest -n0`（单 worker；实测 `build_minimal_app(chats)` ~118MB，`app.main` ~439MB）
- E2E（真实 LLM API）：`uv run pytest -m e2e`（含 `tests/api/agent/test_auto_capture_hooks_e2e.py`、`test_bash_terminal_streaming_e2e.py`）
- 并行（内存充足时）：`PYTEST_XDIST_WORKERS=4 scripts/dev/run_tests_low_memory.sh`；避免 `-n auto`（多 worker RSS 叠加，`-n auto` 在 8 核上可达数 GB）
- 定位高内存文件：`uv run python scripts/dev/profile_test_memory.py tests/api/agent --top 20`
- Playwright UI 测试在 `myrm-agent-frontend/tests/e2e/`（`bun run test:e2e`；CI：`scripts/ci/run_frontend_e2e.sh`；Instinct Inbox 依赖 `POST /api/v1/skills/drafts/test/seed-mock?agent_id=`，**不** mock `/approvals`）
- CI 默认套件：`scripts/ci/run_default_tests.sh`（`-m 'not e2e' -n0`，workflow `server-unit-tests.yml`）
- `tests/api/skills/test_drafts_seed_mock.py`：seed-mock HTTP 单测（含 `agent_id` 查询参数，默认套件执行）
- `tests/api/approvals/test_list_pending_growth_filter.py`：`GET /approvals` 排除后台 growth、保留 inline `thread_id` skill_draft
- `tests/api/skills/conftest.py`：minimal app 含 drafts/curator/sync/evolution/skill-growth 路由
- `tests/api/integrations/test_llm_speed_test.py`：`POST /api/v1/integrations/llm/speed-test`
- `tests/api/notifications/conftest.py`：in-memory DB + loopback auth（通知 API 集成测）
- `tests/api/config/test_readiness_e2e.py`、`tests/api/security/test_generate_policy_e2e.py`：`@pytest.mark.e2e`（默认套件不收集）

## 依赖

- `tests/conftest.py` → `tests/support/test_secrets.py`（**唯一** [T] 加载入口）
- 新 API/集成测优先 `from tests.support.minimal_app import build_minimal_app` + `preset_for_test_path()`，禁止 `from app.main import app`
- `tests/conftest.py` autouse → harness `reset_global_browser_pool_for_tests()`（防 Chromium 跨测累积）
- `app/startup/env_loader.py` **不**读取 `.env.test`
