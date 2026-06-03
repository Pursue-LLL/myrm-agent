# myrm-agent 模块架构

## 架构概述

MIT 开源产品仓，包含 `myrm-agent-server`（业务后端）、`myrm-agent-frontend`（Web UI）、`myrm-agent-desktop`（Tauri 桌面）。Agent 执行引擎来自闭源 `myrm-agent-harness`（PyPI `compiled-core`）。桌面安装包发布于 [Pursue-LLL/myrm-agent Releases](https://github.com/Pursue-LLL/myrm-agent/releases)。

## 目录清单

| 目录 | 地位 | 职责 | 部署 |
|------|------|------|------|
| `myrm-agent-server/` | 核心 | FastAPI 业务编排、API、渠道桥接 | Docker / sidecar / 本地 :8080 |
| `myrm-agent-frontend/` | 核心 | Next.js Web UI、设置与对话界面 | 本地 :3000 / 静态导出 |
| `myrm-agent-desktop/` | 核心 | Tauri 壳 + server sidecar | GitHub Releases |

## 模块依赖

- **Harness**：`myrm-agent-server/pyproject.toml` 钉死 PyPI 版本；vortexai 联调可 `git submodule update` 拉 `myrm-agent-harness`
- **Control Plane**：SaaS 场景对接独立闭源仓 `myrm-control-plane`（OAuth、沙箱、计费）
- **Brand**：官网与文档在 `myrm-agent-brand`（`myrm-website` / `myrm-docs`）

子模块详述：

- [myrm-agent-server/README.md](myrm-agent-server/README.md)
- [myrm-agent-frontend/README.md](myrm-agent-frontend/README.md)
- [myrm-agent-desktop/README.md](myrm-agent-desktop/README.md)

## 本地开发

| 平台 | 一键安装 | 启动 |
|------|----------|------|
| macOS / Linux / Git Bash | `curl -fsSL https://myrmagent.ai/install.sh` then `bash` | `myrm start` |
| Windows PowerShell | `irm https://myrmagent.ai/install.ps1` then `iex` | `myrm start` |

- 仓库内：`bash scripts/install.sh` 或 `powershell -ExecutionPolicy Bypass -File scripts/install.ps1`
- vortexai 开发壳：`scripts/install.sh` / `scripts/install.ps1` 会先 init `myrm-agent` submodule
- 安装目录默认 `~/.myrm/myrm-agent`（`MYRM_INSTALL_DIR` 可覆盖）
- WebUI：`http://localhost:3000`

脚本清单见 [scripts/_ARCH.md](scripts/_ARCH.md)。

手动分进程：

```bash
cd myrm-agent-frontend && bun install && bun run dev
cd myrm-agent-server && uv sync --all-extras && DEPLOY_MODE=tauri uv run run.py
```

## 约束

- 业务与 UI 代码在本仓；通用 Agent 框架能力不得下沉到 server
- Harness 版本以 `uv.lock` + PyPI 为准，CI 校验见 vortexai `scripts/ci/check_harness_on_pypi.py`
- 在 vortexai 中本目录为 **git submodule**；改代码后在本仓 commit/push，再回到 vortexai bump 指针
