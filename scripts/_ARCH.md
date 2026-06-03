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
| `myrm` | Unix | `start` / `stop` / `status` / `update` / `searxng` |
| `myrm.ps1` | Windows | 同上；`start` 优先 `.venv\Scripts\python.exe` |
| `lib/resolve_agent_root.sh` | Unix | vortexai submodule 与 OSS 根路径解析 |
| `lib/start_server.sh` | Unix | `myrm start`：优先 `.venv` python，再 `uv run` |

## 约束

- 默认克隆到 `~/.myrm/myrm-agent`（Windows：`%USERPROFILE%\.myrm\myrm-agent`）
- 需预装 Git；Windows 可选 VS Build Tools（`advanced-tools` extra）
- Harness 来自 PyPI（`uv sync`）；安装后执行 `assert_distribution_ready()`
- `MYRM_INSTALL_SKIP_FRONTEND=1`：CI 跳过后端以外步骤（见 `.github/workflows/install-smoke.yml`）
