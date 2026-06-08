# scripts 模块架构

## 架构概述

OSS 安装与生命周期 CLI。`myrmagent.ai/install.sh` 与 `install.ps1` 经 Vercel 307 指向本仓 `install-remote.*`，再执行 `install.*`。

## 文件清单

| 文件 | 平台 | 职责 |
|------|------|------|
| `install.sh` | Unix / Git Bash | 安装 uv、bun；`uv sync`；前端 build；注册 `myrm` |
| `install-remote.sh` | Unix | `curl \| bash` 入口：clone → `install.sh` |
| `install.ps1` | Windows | 同上（PowerShell 原生） |
| `install-remote.ps1` | Windows | `irm \| iex` 入口：clone → `install.ps1` |
| `myrm` | Unix | `setup` / `dev` / `start` / `stop` / `status` / `update` / `doctor` / `searxng`（PyPI harness） |
| `dev/dev.sh` | Unix | `myrm dev`：仅后端 :8080 |
| `dev/start.sh` | Unix | `myrm start`：后端 :8080 + 前端 `bun run dev` :3000 |
| `myrm.ps1` | Windows | 同上；`start` 优先 `.venv\Scripts\python.exe` |
| `dev/setup.sh` / `setup.ps1` | 双平台 | clone 后首次：`uv sync` + `patchright install chromium` + `bun install`（PyPI harness） |
| `dev/run_server.sh` / `run_server.ps1` | 双平台 | 开发启动后端（与 `myrm start` 同策略） |
| `lib/resolve_agent_root.sh` | Unix | 嵌套目录与独立 clone 的根路径解析 |
| `lib/start_server.sh` | Unix | `run_server.sh` 用手动启动；日常用 `myrm dev` / `myrm start` |
| `dev/test-instinct-inbox-seed.py` | 双平台 | Instinct Inbox E2E：向运行中后端 POST seed-mock（或 `--direct` 直写 DB） |
| `dev/test-instinct-inbox-e2e.sh` | Unix | Instinct Inbox 全链路：pytest API + Playwright UI（依赖 `myrm dev`） |
| `maintainer/` | — | **OSS 仓无脚本**；代码生成在闭源 `myrm-agent-harness/scripts/maintainer/`（如 `generate_litellm_routing.py`）。前端仅提交生成产物。见 [maintainer/_ARCH.md](maintainer/_ARCH.md) |

## 约束

- 默认克隆到 `~/.myrm/myrm-agent`（Windows：`%USERPROFILE%\.myrm\myrm-agent`）
- 需预装 Git；Windows 原生扩展编译失败时以 `uv sync` 核心依赖为准（harness 已含 retrieval 等 extras）
- Harness 来自 PyPI（`uv sync`）；安装后执行 `assert_distribution_ready()`
- `MYRM_INSTALL_SKIP_FRONTEND=1`：CI 跳过后端以外步骤（见 `.github/workflows/install-smoke.yml`）
