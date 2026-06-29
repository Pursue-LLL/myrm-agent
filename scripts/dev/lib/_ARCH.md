# scripts/dev/lib 模块架构

## 架构概述

`scripts/dev/` 专用 Bash 辅助。与根级 [scripts/lib/_ARCH.md](../../lib/_ARCH.md) 区分：根 `lib/` 供 `myrm` 主 CLI 使用；本目录供 `dev.sh` / `start.sh` source。

## 文件清单

| 文件 | 职责 |
|------|------|
| `backend_bg.sh` | 后台启动 `myrm-agent-server`（:8080）；写 `.myrm-dev-backend.pid` / `.myrm-dev-backend.log`；健康检查轮询 |

## 依赖

- [scripts/dev/_ARCH.md](../_ARCH.md)
- [scripts/dev/dev.sh](../dev.sh) · [scripts/dev/start.sh](../start.sh) — source `backend_bg.sh`
