# scripts/ci 模块架构

## 架构概述

OSS 仓库 CI 辅助脚本（非运行时）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `install-pre-push-hook.sh` | 安装 git pre-push 钩子，本地推送前跑架构守门 |
| `desktop-release/` | 桌面发版 CI 脚本 · [desktop-release/_ARCH.md](desktop-release/_ARCH.md) |

## 依赖

- 父模块 [scripts/_ARCH.md](../_ARCH.md)
- Server CI：`myrm-agent-server/scripts/ci/lib_harness_deps.sh`、`run_architecture_gates.sh`、`run_default_tests.sh`
