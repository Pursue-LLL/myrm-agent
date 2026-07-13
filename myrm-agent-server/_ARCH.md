# myrm-agent-server 模块架构

FastAPI 单机业务后端：HTTP API、渠道桥接、生命周期编排；Agent 执行内核来自 PyPI `myrm-agent-harness`。

整体架构、分形文档规范与启动序见 **[ARCHITECTURE.md](ARCHITECTURE.md)**；GitHub 快速启动见 **[README.md](README.md)**。

## 目录清单

| 目录 | 地位 | 职责 |
|------|------|------|
| `app/` | 核心 | 业务源码（api / services / channels / core 等）· [app/_ARCH.md](app/_ARCH.md) |
| `scripts/` | 辅助 | 部署 CLI、分形/行数门禁、CI 脚本 · [scripts/_ARCH.md](scripts/_ARCH.md) |
| `tests/` | 辅助 | 单元 / 集成 / 架构守门 · [tests/_ARCH.md](tests/_ARCH.md) |
| `assets/` | 辅助 | 预置 Agent/Skill/Cookbook 静态资源 · [assets/_ARCH.md](assets/_ARCH.md) |
| `docker/` | 辅助 | Server 与 Skill Sandbox 镜像 · [docker/_ARCH.md](docker/_ARCH.md) |
| `deployments/` | 辅助 | 可选运维栈（如 Prometheus）· [deployments/_ARCH.md](deployments/_ARCH.md) |
| `searxng/` | 辅助 | 本地 SearXNG 配置 · [searxng/_ARCH.md](searxng/_ARCH.md) |
| `data/` | 运行时 | 本地 dev 向量/记忆数据（gitignore） |
| `.agent/` | 运行时 | Harness workspace 树（`.agent/docs`、`.agent/vault`；gitignore，勿与包根 `.myrm/` 混淆） |

## 根级入口

| 文件 | 职责 |
|------|------|
| `run.py` | 进程 CLI 入口 → `app/startup/*` |
| `deploy.py` | 薄 shim → `scripts/deploy.py` |
| `pyproject.toml` / `uv.lock` | Python 依赖与 harness PyPI pin |
| `Dockerfile` / `docker-compose.yaml` | 容器构建与编排 |

## 约束

- 禁止 vendoring harness；版本以 `uv.lock` 为准
- 通用 Agent 框架能力不得在本包重复实现
- `app/core|services|lifecycle` 禁止 import `app.api`（见 [ARCHITECTURE.md §0.10](ARCHITECTURE.md)）
