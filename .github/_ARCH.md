# .github 模块架构

## 架构概述

OSS `myrm-agent` 仓库 GitHub Actions 工作流与 CI 配置根。

## 子目录

| 目录 | 职责 |
|------|------|
| `workflows/` | CI/CD 流水线（server 测试、架构守门、安装冒烟、`desktop-release` 等） |

## 依赖

- [scripts/ci/_ARCH.md](../scripts/ci/_ARCH.md) — pre-push 钩子
- Server 架构守门：`myrm-agent-server/scripts/ci/run_architecture_gates.sh`
