# tests 模块架构

pytest 测试套件根目录。单元/集成/API/E2E 测试按域分子目录；[T] 业务密钥仅通过结构化 fixture 加载，不进入 server 运行时。

---

## 文件清单

| 路径 | 地位 | 职责 |
|------|------|------|
| `conftest.py` | 核心 | 进程级 `.env` + [T] secrets bootstrap、隔离 workspace、`test_secrets` session fixture、每测后 `GlobalBrowserPool.shutdown()` |
| `support/test_secrets.py` | 核心 | [T] `.env.test` 结构化加载（`TestSecrets`、`load_test_secrets`、`resolve_test_env`） |
| `api/agent/utils.py` | 辅助 | Agent 测试共享工具（模型/搜索配置组装） |
| `e2e/conftest.py` | 辅助 | E2E ephemeral server fixture（API 级 e2e，不启动前端） |
| `benchmarks/bench_mcp_ptc_vs_direct.py` | 基准 | MCP PTC vs 直连 token/延迟对比；凭据仅来自 `.env.test` |
| `fixtures/cp_proxy_signature_contract.json` | 辅助 | 控制服务反向代理 HMAC 契约向量（server 侧自包含） |

---

## [T] 测试密钥约定

1. 开发者复制 `myrm-agent-server/.env.test.example` → `.env.test`（gitignored）
2. `tests/conftest.py` 调用 `apply_test_secrets_to_environ()` 供 legacy `skipif(os.getenv(...))` 兼容
3. 新测试优先使用 `test_secrets` fixture 或 `resolve_test_env()`，禁止在源码中硬编码密钥
4. 权威变量索引：`.env.example`（[P/O]）、`.env.sandbox.example`（[S]）、`.env.test.example`（[T]）

---

## 测试分层（默认 `pytest`）

- 默认 `addopts`：`-m 'not e2e'`（跳过需真实 LLM / 长链路 e2e）
- 单元 + API 集成：直接 `uv run pytest`
- E2E（真实 LLM API）：`uv run pytest -m e2e`
- 并行（内存充足时）：`uv run pytest -n auto`
- Playwright / 真实 Chromium UI 测试已移出 `tests/`（不再随默认套件收集）

## 依赖

- `tests/conftest.py` → `tests/support/test_secrets.py`（**唯一** [T] 加载入口）
- `tests/conftest.py` autouse：每测后 `GlobalBrowserPool.shutdown()`（防 Chromium 进程跨测累积）
- `app/startup/env_loader.py` **不**读取 `.env.test`
