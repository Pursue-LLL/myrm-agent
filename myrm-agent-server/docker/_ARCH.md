# docker/ 模块架构

## 架构概述

Server 容器构建与运行时入口。`Dockerfile` 从 PyPI 安装钉死版本；`Dockerfile.official` 从 harness 源码构建 wheel 后装入镜像（发布流水线使用）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `Dockerfile` | 核心 | OSS 镜像：uv sync + PyPI 安装 harness + runtime verify | ✅ |
| `Dockerfile.official` | 核心 | 源码构建 harness wheel 后装入 server venv | ✅ |
| `read_harness_pypi_spec.py` | 辅助 | 从 `pyproject.toml` 解析 harness pip 规格（Dockerfile / 安装脚本共用） | ✅ |
| `install_harness_wheels.sh` | 核心 | `Dockerfile.official` builder：按平台安装 core/release 双 wheel | ✅ |
| `entrypoint.sh` | 核心 | 容器启动入口（Xvfb/VNC 等） | ✅ |
| `sandbox/` | 子模块 | Skill 沙箱镜像（与 server runtime 分离） | ✅ |

## 公开 Dockerfile

构建上下文为 **myrm-agent-server 仓库根**：

```bash
docker build -t myrm-server .
```

Builder：`uv sync --frozen --all-extras`（含 `compiled-core`）；PyPI 未发布时 CI 失败（无 silent fallback）。Runtime：`verify-harness-distribution --matplotlib-cjk`。

Lock 约束：`tests/architecture/test_uv_lock_harness_registry.py` 要求 `uv.lock` 使用 PyPI registry pin。

CI（本仓）：`myrm-agent-server/.github/workflows/test.yml`；产品仓根 `myrm-agent/.github/workflows/install-smoke.yml`（`uv sync --frozen` 需 PyPI 上 harness 已发布）。

Harness 版本与 wheel 矩阵见下方链接；升级 server 依赖时在 `myrm-agent-server` 对 PyPI 已发布版本更新 `pyproject.toml` 并刷新 `uv.lock`。

## 参考

- [DISTRIBUTION_SYSTEM.md](https://github.com/Pursue-LLL/myrm-agent-harness/blob/main/harness_packaging/DISTRIBUTION_SYSTEM.md)
