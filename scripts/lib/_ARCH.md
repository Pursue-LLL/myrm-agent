# scripts/lib 模块架构

## 架构概述

`myrm` CLI 与 `scripts/dev/*` 共享的 Bash 库。仅 Unix/Git Bash；Windows 使用 PowerShell 对等脚本。

## 文件清单

| 文件 | 职责 |
|------|------|
| `resolve_agent_root.sh` | 解析嵌套 monorepo 与独立 clone 下的 `myrm-agent` 根路径 |
| `start_server.sh` | 启动 FastAPI 后端（env、端口、venv python） |

## 依赖

- 父模块 [scripts/_ARCH.md](../_ARCH.md)
