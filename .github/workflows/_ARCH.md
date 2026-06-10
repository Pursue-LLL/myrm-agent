# .github/workflows 模块架构

## 架构概述

GitHub Actions 工作流定义。关键流水线包括 server 架构守门（`server-architecture.yml`）、server 默认 pytest（`server-unit-tests.yml`）、`frontend-build.yml`（PR `next build`）、`frontend-e2e.yml`（PR Playwright）、安装脚本冒烟、`desktop-release.yml`（`v*` tag → mac ARM 先发 Release → Win/Linux 追加 → `scripts/ci/desktop-release/finalize-release.sh` 生成 `latest.json` + `.sha256`）。

## 约束

- OSS `main` 分支 `uv.lock` 须 PyPI registry pin harness（见 `tests/architecture/test_uv_lock_harness_registry.py`）
- 架构测试标记 `@pytest.mark.architecture`

## 依赖

- 父模块 [../_ARCH.md](../_ARCH.md)
