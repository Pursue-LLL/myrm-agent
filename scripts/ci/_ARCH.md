# scripts/ci 模块架构

## 架构概述

OSS 仓库 CI 辅助脚本（非运行时）。当前仅 pre-push 钩子安装。

## 文件清单

| 文件 | 职责 |
|------|------|
| `install-pre-push-hook.sh` | 安装 git pre-push 钩子，本地推送前跑架构守门 |

## 依赖

- 父模块 [scripts/_ARCH.md](../_ARCH.md)
- Server 架构测试：`myrm-agent-server/scripts/ci/run_architecture_gates.sh`
