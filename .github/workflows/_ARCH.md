# .github/workflows 模块架构

## 架构概述

GitHub Actions 工作流定义。关键流水线包括 server 架构守门（`server-architecture.yml`）、server 默认 pytest（`server-unit-tests.yml`）、`frontend-build.yml`（PR `next build`）、`frontend-e2e.yml`（PR Playwright）、安装脚本冒烟、`desktop-release.yml`（`v*` tag → `prepare-frontend` → `check-updater-pubkey.sh` → mac ARM 先发 Release → mac Intel + Win/Linux 追加包与 `.sig`（`collect-bundle-assets.sh` + Bash 3.2 `while read` 上传）→ `finalize-release.sh`（无 `.sig` 不进 OTA manifest）→ 可选 `trigger-website-release.sh`，`REQUIRE_WEBSITE_DEPLOY=false`）。

## 约束

- OSS `main` 分支 `uv.lock` 须 PyPI registry pin harness（见 `tests/architecture/test_uv_lock_harness_registry.py`）
- 架构测试标记 `@pytest.mark.architecture`

## 依赖

- 父模块 [../_ARCH.md](../_ARCH.md)
