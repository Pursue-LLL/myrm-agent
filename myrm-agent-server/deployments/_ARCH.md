# deployments/ 模块架构

## 架构概述

可选运维栈配置片段，**非** `deploy.py` 主部署路径的一部分。当前仅含 Prometheus 告警规则示例。

## 文件清单

| 路径 | 职责 |
|------|------|
| `prometheus/rules.yml` | Prometheus 告警规则示例（含 `myrm_memory_brief_*` not_applied/unknown 告警） |

## 依赖

- 主部署入口：[scripts/deploy.py](../scripts/deploy.py) · [scripts/_ARCH.md](../scripts/_ARCH.md)
