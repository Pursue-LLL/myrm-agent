# docker/ 模块架构

## 架构概述

Server 容器构建与运行时入口。开源路径不包含 harness 源码；`Dockerfile` 从 PyPI 安装钉死版本，`Dockerfile.official` 在私有 CI 内从 harness 源码装配 wheel。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `Dockerfile` | 核心 | OSS 镜像：uv sync + PyPI 安装 harness + runtime verify | ✅ |
| `Dockerfile.official` | 核心 | 私有 CI：源码构建 harness wheel 后装入 server venv | ✅ |
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

CI：`.github/workflows/build-oss-server-docker.yml`（require PyPI + 无 PAT）。

## Harness PyPI

发布：`myrm-agent-harness/.github/workflows/publish-pypi.yml`（tag `v*` → post-verify 7 包）。

Harness 专属 CI：私有仓 `arm64-build.yml`、`performance.yml`、`security.yml`、`build-official-runtime.yml`。

消费前检查：`scripts/ci/require_harness_on_pypi.sh`（server / docker / tauri CI）。

## 参考

- [DISTRIBUTION_SYSTEM.md](https://github.com/Pursue-LLL/myrm-agent-harness/blob/main/harness_packaging/DISTRIBUTION_SYSTEM.md)
