# .github 模块架构

## 架构概述

OSS `myrm-agent` 仓库 GitHub Actions 工作流与 CI 配置根。

## 子目录

| 目录 | 职责 |
|------|------|
| `workflows/` | CI/CD 流水线（harness 测试/架构/发布、server 测试、架构守门、安装冒烟、`desktop-release` 等） |

## 文件

| 文件 | 职责 |
|------|------|
| `secret_scanning.yml` | 密钥扫描与推送保护的路径排除：仅列出刻意含有仿真假密钥的脱敏/泄露防护测试夹具文件，逐文件列出，不排除整个目录 |
| `core-platform-matrix.json` | harness 平台 core wheel 的构建矩阵（8 个平台，含 2 个 musl）：`harness-publish.yml` 的 `prepare-matrix` job 读取它，与 `myrm-agent-harness/harness_packaging/platforms.py` 的 `PUBLISH_PLATFORMS` 保持一致 |

## 依赖

- [scripts/ci/_ARCH.md](../scripts/ci/_ARCH.md) — pre-push 钩子
- Server 架构守门：`myrm-agent-server/scripts/ci/run_architecture_gates.sh`
