# docker/ 模块架构

## 架构概述

Server 容器构建与运行时入口。两个 Dockerfile 都从本仓库源码构建：先用 `myrm-agent-harness/` 构建单个纯 Python wheel（与发往 PyPI 的产物同形），再以 `uv.lock` 安装其余全部依赖并装入该 wheel。`Dockerfile` 是面向自托管用户的镜像（root 启动 + `gosu` 降权，支持国内镜像构建参数）；`Dockerfile.official` 是云托管运行时镜像（`USER myrm` 非 root）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `../Dockerfile` | 核心 | 自托管镜像：harness wheel 阶段 + `uv sync --frozen`（跳过 harness 本体）+ wheel 安装 + runtime verify | ✅ |
| `Dockerfile.official` | 核心 | 云托管运行时镜像：同上构建链，非 root 运行 | ✅ |
| `entrypoint.sh` | 核心 | 容器启动入口（Xvfb/VNC/D-Bus + export DISPLAY） | ✅ |
| `sandbox/` | 子模块 | Skill 沙箱镜像（与 server runtime 分离） | ✅ |

## 构建

云托管运行时镜像由 CP 契约 `DEFAULT_AGENT_SERVER_IMAGE` 指向 `Dockerfile.official` 产物；Skill 沙箱镜像由 `sandbox/Dockerfile` 独立构建；`docker-compose.yaml` 不含 agent 镜像 profile。

**PID-1 治理（tini）**：三个 Dockerfile 均以 `/usr/bin/tini -g --` 作为容器 PID-1（`ENTRYPOINT`）：
- `Dockerfile` / `Dockerfile.official`：`tini -g -- /app/entrypoint.sh`，`-g` 让 tini 转发信号到整个进程组（配合 `entrypoint.sh` 内 Xvfb/VNC 等长驻子进程优雅退出）；`entrypoint.sh` 依 `$UID` 走 `gosu`（root 本地）或 `exec "$@"`（`USER myrm`）分支。
- `sandbox/Dockerfile`：`tini -g --` + `USER sandbox`，tini 以非 root 运行（同 uid 收割/转发，最小权限）。
- 云托管容器由 CP 契约以 `Entrypoint: ["/usr/bin/tini","-g","--","/bin/sh","-c"]` 覆盖镜像 ENTRYPOINT（root init shell → `runuser -u myrm` 降权）；`CapAdd` 含 `KILL`（runuser 降权后 tini 向 uid≠0 子进程转发信号所需）。

构建上下文为 **myrm-agent 仓库根**（含 `myrm-agent-harness/`、`myrm-agent-server/` 与 `shared/`，与 `docker-compose.yaml` backend build `context: ..` 一致）：

```bash
docker build -f myrm-agent-server/Dockerfile -t myrm-server .
docker build -f myrm-agent-server/docker/Dockerfile.official -t myrm/runtime:local .
```

Runtime 阶段 `COPY shared /shared`，供 [providers.py](../app/services/agent/params/providers.py) 在 `/shared/config/provider_legacy_remap.json` 加载跨端 provider ID remap。

依赖安装：`uv.lock` 把 harness 解析为本仓库 editable path source；镜像内用 `uv sync --frozen --all-extras --no-install-package myrm-agent-harness` 装其余依赖（harness 的依赖仍来自 lock），再 `uv pip install --no-deps` 装入 harness wheel，因此镜像里的 harness 不是 editable。Runtime 校验：`verify-harness-distribution --matplotlib-cjk`。

Lock 约束：`tests/architecture/test_server_pyproject_lock_parity.py` 要求 harness 为 in-repo path source，且 `uv.lock` 只使用 `pypi.org` / `files.pythonhosted.org`（不含镜像站 URL）。

CI：`.github/workflows/server-architecture.yml`（PR 全 paths；`main` push 仅分发 paths 触发 `docker-image` job：仓库根 `docker build -f myrm-agent-server/Dockerfile`，容器内 smoke import provider remap）；`install-smoke.yml`（`install.sh` 非 frozen 路径；Windows 仅 `workflow_dispatch`）。

升级 harness 依赖：改 `myrm-agent-harness/pyproject.toml` 后分别刷新 `myrm-agent-harness/uv.lock` 与 `myrm-agent-server/uv.lock`；harness 与 server 同仓同提交，无需先发 PyPI。
