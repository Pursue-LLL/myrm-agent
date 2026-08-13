# .github/workflows 模块架构

## 架构概述

GitHub Actions 工作流定义。关键流水线包括 server 架构守门（`server-architecture.yml`，含 fractal docs + ruff lint + `promtool check rules` + architecture pytest）、server 默认测试（`server-unit-tests.yml`，含 ruff lint + 默认 pytest）、`frontend-build.yml`（PR oxlint + `next build`）、`desktop-fractal-docs.yml`（桌面 `_ARCH` 清单 gate）、安装脚本冒烟、`desktop-release.yml`（`v*` tag → 四平台包 + OTA `latest.json`）；官网部署在 `myrm-agent-brand` 打 `website-v*` tag，不在 agent 仓。WebUI E2E 走 MCP chrome-devtools，禁止 `@playwright/test` CI 流水线。lint 门禁：前端 `bun run lint`（oxlint，errors 阻断）、后端 `ruff check .`（architecture 与 default 双路径全覆盖）。

## 约束

- OSS `main` 分支 `uv.lock` 须 PyPI registry pin harness（见 `tests/architecture/test_uv_lock_harness_registry.py`）
- 架构测试标记 `@pytest.mark.architecture`

## 依赖

- 父模块 [../_ARCH.md](../_ARCH.md)
