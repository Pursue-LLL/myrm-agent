# .github/workflows 模块架构

## 架构概述

GitHub Actions 工作流定义。关键流水线包括 server 架构守门（`server-architecture.yml`，含 fractal docs + ruff lint + `promtool check rules` + architecture pytest）、server 默认测试（`server-unit-tests.yml`，含 ruff lint + 默认 pytest）、`frontend-build.yml`（push main 与 PR：`i18n:split` 生成物前置，其后 oxlint / strict TS / fractal docs / barrel / module resolution / i18n / vitest / `next build`（含 SW Web Push 校验）各门禁独立执行）、`desktop-fractal-docs.yml`（桌面 `_ARCH` 清单 gate）、安装脚本冒烟、`desktop-release.yml`（`v*` tag → 四平台包 + OTA `latest.json`）；官网部署在 `myrm-agent-brand` 打 `website-v*` tag，不在 agent 仓。WebUI E2E 走 MCP chrome-devtools，禁止 `@playwright/test` CI 流水线。lint 门禁：前端 `bun run lint`（oxlint，errors 阻断）、后端 `ruff check .`（architecture 与 default 双路径全覆盖）。

## 约束

- OSS `main` 分支 `uv.lock` 须 PyPI registry pin harness（见 `tests/architecture/test_uv_lock_harness_registry.py`）
- 架构测试标记 `@pytest.mark.architecture`
- 第三方 action 一律钉 40 位 commit SHA 并在行尾注释对应的 tag（`dtolnay/rust-toolchain` 钉 `stable` 分支头，注释 `stable`）；SHA 必须由 `git ls-remote --tags <仓库> refs/tags/<tag> refs/tags/<tag>^{}` 解出（`stable` 用 `git ls-remote <仓库> refs/heads/stable`），禁止手写或凭记忆填写（解析不到的 SHA 会让 job 在 `Set up job` 阶段直接失败）

## 依赖

- 父模块 [../_ARCH.md](../_ARCH.md)
