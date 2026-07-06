# .github/workflows 模块架构

## 架构概述

GitHub Actions 工作流定义。关键流水线包括 server 架构守门（`server-architecture.yml`）、server 默认 pytest（`server-unit-tests.yml`）、`frontend-build.yml`（PR `next build`）、`desktop-fractal-docs.yml`（桌面 `_ARCH` 清单 gate）、安装脚本冒烟、`desktop-release.yml`（`v*` tag → 四平台包 + OTA `latest.json`）；官网部署在 `myrm-agent-brand` 打 `website-v*` tag，不在 agent 仓。WebUI E2E 走 MCP chrome-devtools，禁止 `@playwright/test` CI 流水线。

## 约束

- OSS `main` 分支 `uv.lock` 须 PyPI registry pin harness（见 `tests/architecture/test_uv_lock_harness_registry.py`）
- 架构测试标记 `@pytest.mark.architecture`

## 依赖

- 父模块 [../_ARCH.md](../_ARCH.md)
