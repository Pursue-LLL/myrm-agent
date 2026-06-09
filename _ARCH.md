# myrm-agent 模块架构

## 架构概述

MIT 开源产品仓，包含 `myrm-agent-server`（业务后端）、`myrm-agent-frontend`（Web UI）、`myrm-agent-desktop`（Tauri 桌面）、`myrm-agent-extension`（Chrome MV3 浏览器桥）。运行时通过 `uv.lock` 安装 `myrm-agent-harness`（PyPI）。五仓边界、三部署模式与启动序见 **[ARCHITECTURE.md](ARCHITECTURE.md)**；贡献流程见 **[CONTRIBUTING.md](CONTRIBUTING.md)**。桌面安装包发布于 [Pursue-LLL/myrm-agent Releases](https://github.com/Pursue-LLL/myrm-agent/releases)。

## 根目录文件

| 文件 | 职责 |
|------|------|
| `LICENSE` | MIT 许可（全仓） |
| `CONTRIBUTING.md` | OSS 贡献指南 |
| `SECURITY.md` | 漏洞报告策略 |
| `ARCHITECTURE.md` | 五仓边界、三部署模式、文档索引 |
| `_ARCH.md` | 本文件：子目录职责表 |

## 目录清单

| 目录 | 地位 | 职责 | 部署 |
|------|------|------|------|
| `shared/` | 辅助 | 前后端共享静态契约（如 provider ID remap）；Docker `COPY shared /shared` | 随仓分发 |
| `myrm-agent-server/` | 核心 | FastAPI 业务编排、API、渠道桥接 | Docker / sidecar / 本地 :8080 |
| `myrm-agent-frontend/` | 核心 | Next.js Web UI、设置与对话界面 | 本地 :3000 / 静态导出 · [\_ARCH.md](myrm-agent-frontend/_ARCH.md) |
| `myrm-agent-desktop/` | 核心 | Tauri 壳 + server sidecar | GitHub Releases |
| `myrm-agent-extension/` | 辅助 | Chrome MV3 浏览器 CDP 桥（WebSocket 客户端） | 开发者 unpacked / 未来商店 · [\_ARCH.md](myrm-agent-extension/_ARCH.md) |

## 模块依赖

- **依赖**：`pyproject.toml` + `uv.lock` 钉死 PyPI 版本（`myrm setup` / `uv sync`）

子模块详述（架构文档优先于 README）：

- [myrm-agent-server/ARCHITECTURE.md](myrm-agent-server/ARCHITECTURE.md)
- [myrm-agent-frontend/src/components/_ARCH.md](myrm-agent-frontend/src/components/_ARCH.md)
- [myrm-agent-desktop/_ARCH.md](myrm-agent-desktop/_ARCH.md)
- [myrm-agent-extension/_ARCH.md](myrm-agent-extension/_ARCH.md)

## 本地开发

| 平台 | 一键安装 | 启动 |
|------|----------|------|
| macOS / Linux / Git Bash | `curl -fsSL https://myrmagent.ai/install.sh` then `bash` | `myrm start` |
| Windows PowerShell | `irm https://myrmagent.ai/install.ps1` then `iex` | `myrm start` |

- 仓库内：`bash scripts/install.sh` 或 `powershell -ExecutionPolicy Bypass -File scripts/install.ps1`，或 `myrm setup`
- 安装目录默认 `~/.myrm/myrm-agent`（`MYRM_INSTALL_DIR` 可覆盖）
- WebUI：`http://localhost:3000`

脚本清单见 [scripts/_ARCH.md](scripts/_ARCH.md)。

手动分进程：

```bash
cd myrm-agent-frontend && bun install && bun run dev
myrm setup && myrm start
```

## 约束

- 业务与 UI 代码在本仓；通用 Agent 框架能力不得下沉到 server
- Harness 版本以 `uv.lock` + PyPI 为准；发布流水线在刷新 lock 前校验 PyPI 上包是否齐全
