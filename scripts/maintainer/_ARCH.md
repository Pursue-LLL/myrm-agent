# scripts/maintainer/

## 架构概述

**本目录在 MIT 开源仓中为空。** 代码生成脚本在 PyPI `myrm-agent-harness` 维护者工具链中运行，产物提交到本仓。

## 生成物消费点（OSS）

| 生成脚本（harness） | 提交在 myrm-agent 的路径 |
|---------------------|---------------------------|
| `generate_litellm_routing.py` | `myrm-agent-frontend/src/store/config/litellmRouting.generated.ts` |

发布前在 harness 仓运行生成器，再将产物提交到本仓；勿在 OSS 复制 maintainer 脚本以免双源漂移。
