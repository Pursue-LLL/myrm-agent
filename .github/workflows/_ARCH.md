# .github/workflows 模块架构

## 架构概述

GitHub Actions 工作流定义。关键流水线包括 server 架构/分形文档守门（`shared/**`、`assets/**` 变更亦触发）、`frontend-build.yml`（`next build`，`shared/**` 变更亦触发）、安装脚本冒烟。

## 约束

- OSS `main` 分支 `uv.lock` 须 PyPI registry pin harness（见 `tests/architecture/test_uv_lock_harness_registry.py`）
- 架构测试标记 `@pytest.mark.architecture`

## 依赖

- 父模块 [../_ARCH.md](../_ARCH.md)
