# docker/ 模块架构

## 架构概述

Server 容器构建与运行时入口。`Dockerfile` 从 PyPI 安装钉死版本；`Dockerfile.official` 从 harness 源码构建 wheel 后装入镜像（发布流水线使用）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `Dockerfile` | 核心 | OSS 镜像：uv sync + PyPI 安装 harness + runtime verify | ✅ |
| `Dockerfile.official` | 核心 | 源码构建 harness wheel 后装入 server venv | ✅ |
| `read_harness_pypi_spec.py` | 辅助 | 从 `pyproject.toml` 解析 harness pip 规格（安装脚本 / CI 共用；公开 Dockerfile 仅用 `uv.lock`） | ✅ |
| `install_harness_wheels.sh` | 核心 | `Dockerfile.official` builder：按平台安装 core/release 双 wheel | ✅ |
| `entrypoint.sh` | 核心 | 容器启动入口（Xvfb/VNC/D-Bus + export DISPLAY） | ✅ |
| `sandbox/` | 子模块 | Skill 沙箱镜像（与 server runtime 分离） | ✅ |

## 公开 Dockerfile

云托管运行时镜像由 CP 契约 `DEFAULT_AGENT_SERVER_IMAGE` 指向 `Dockerfile.official` 产物；Skill 沙箱镜像由 `sandbox/Dockerfile` 独立构建；`docker-compose.yaml` 不含 agent 镜像 profile。

**PID-1 治理（tini）**：三个 Dockerfile 均以 `/usr/bin/tini -g --` 作为容器 PID-1（`ENTRYPOINT`）：
- `Dockerfile` / `Dockerfile.official`：`tini -g -- /app/entrypoint.sh`，`-g` 让 tini 转发信号到整个进程组（配合 `entrypoint.sh` 内 Xvfb/VNC 等长驻子进程优雅退出）；`entrypoint.sh` 依 `$UID` 走 `gosu`（root 本地）或 `exec "$@"`（`USER myrm`）分支。
- `sandbox/Dockerfile`：`tini -g --` + `USER sandbox`，tini 以非 root 运行（同 uid 收割/转发，最小权限）。
- 云托管容器由 CP 契约以 `Entrypoint: ["/usr/bin/tini","-g","--","/bin/sh","-c"]` 覆盖镜像 ENTRYPOINT（root init shell → `runuser -u myrm` 降权）；`CapAdd` 含 `KILL`（runuser 降权后 tini 向 uid≠0 子进程转发信号所需）。

构建上下文为 **myrm-agent 仓库根**（含 `myrm-agent-server/` 与 `shared/`，与 `docker-compose.yaml` backend build `context: ..` 一致）：

```bash
docker build -f myrm-agent-server/Dockerfile -t myrm-server .
```

Runtime 阶段 `COPY shared /shared`，供 [providers.py](../app/services/agent/params/providers.py) 在 `/shared/config/provider_legacy_remap.json` 加载跨端 provider ID remap。

`Dockerfile.official` 全部 `COPY` 使用 `myrm-agent/myrm-agent-server/` 前缀；runtime `COPY myrm-agent/shared /shared`。构建上下文为 open-perplexity / vortexai 根目录（`.`），与根 [docker-compose.yml](../../../docker-compose.yml) 一致：

```bash
docker build -f myrm-agent/myrm-agent-server/docker/Dockerfile.official -t myrm/runtime:local .
```

Builder：`uv sync --frozen --all-extras`（含 `compiled-core`；`pyproject.toml` 设 `prerelease=allow` 与 `index-url=pypi.org`）。PyPI 未发布时 CI 失败（无 silent fallback）。Runtime：`python -m myrm_agent_harness.distribution.verify --matplotlib-cjk`（公开 Dockerfile 不依赖 console script  shim）。

Lock 约束：`tests/architecture/test_uv_lock_harness_registry.py` 要求 `uv.lock` 使用 PyPI registry pin。

CI：`myrm-agent/.github/workflows/server-architecture.yml`（PR 全 paths；`main` push 仅分发 paths 触发 `docker-image` job：monorepo 根 `docker build -f myrm-agent-server/Dockerfile`，容器内 smoke import provider remap）；`install-smoke.yml`（`install.sh` 非 frozen 路径；Windows 仅 `workflow_dispatch`）。

Harness 版本与 wheel 矩阵见下方链接；升级 server 依赖时在 `myrm-agent-server` 对 PyPI 已发布版本更新 `pyproject.toml` 并刷新 `uv.lock`。

## 参考

- [DISTRIBUTION_SYSTEM.md](https://github.com/Pursue-LLL/myrm-agent-harness/blob/main/harness_packaging/DISTRIBUTION_SYSTEM.md)
