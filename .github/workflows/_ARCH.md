# .github/workflows 模块架构

## 架构概述

GitHub Actions 工作流定义。harness 流水线：`harness-test.yml`（单测 + 浏览器集成）、`harness-boundary.yml`（边界/分形文档/布局/架构测试）、`harness-tool-registry.yml`（工具注册一致性，含 server 引导解析）、`harness-performance.yml`（启动性能回归）、`harness-publish.yml`（`harness-v*` tag → 版本校验 → 构建 sdist+wheel → 干净环境 verify → PyPI Trusted Publishing，`environment: pypi`）；均在 `myrm-agent-harness/` 下运行，runner 固定 `ubuntu-24.04`，uv 固定 0.12.7，actions 按已核对的 commit SHA 钉死。关键流水线还包括 server 架构守门（`server-architecture.yml`，含 fractal docs + ruff lint + `promtool check rules` + architecture pytest）、server 默认测试（`server-unit-tests.yml`，含 ruff lint + 默认 pytest）、`frontend-build.yml`（PR oxlint + `next build`）、`desktop-fractal-docs.yml`（桌面 `_ARCH` 清单 gate）、安装脚本冒烟、`desktop-release.yml`（`v*` tag → 四平台包 + OTA `latest.json`）；官网部署在 `myrm-agent-brand` 打 `website-v*` tag，不在 agent 仓。WebUI E2E 走 MCP chrome-devtools，禁止 `@playwright/test` CI 流水线。lint 门禁：前端 `bun run lint`（oxlint，errors 阻断）、后端 `ruff check .`（architecture 与 default 双路径全覆盖）。

## 约束

- server `uv.lock` 把 harness 解析为 in-repo editable path source（见 `myrm-agent-server/tests/architecture/test_server_pyproject_lock_parity.py`）；harness 变更须触发 server 流水线（`server-unit-tests.yml` / `server-architecture.yml` 的 paths 含 `myrm-agent-harness/src/**`、`pyproject.toml`）
- `harness-v*` 与桌面发布 `v*` tag 命名空间互不重叠；发布不使用长期 PyPI token
- 架构测试标记 `@pytest.mark.architecture`

## 依赖

- 父模块 [../_ARCH.md](../_ARCH.md)
