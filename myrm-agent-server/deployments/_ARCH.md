# deployments/ 模块架构

## 架构概述

可选运维栈配置片段，**非** `deploy.py` 主部署路径的一部分。当前仅含 Prometheus 告警规则示例。

## 文件清单

| 路径 | 职责 |
|------|------|
| `prometheus/rules.yml` | Prometheus 告警规则示例（含 `myrm_memory_brief_*` not_applied、stream/persist mismatch、unknown 告警；`MemoryBriefTelemetryFlushHttpErrorDetected` 采用 attempts-based 自适应阈值；`MemoryBriefTelemetryDedupRejectDetected` 补齐 control-plane strict dedup reject 比率/突发告警；由 `tests/architecture/test_memory_brief_prometheus_rules_contract.py` 做契约门禁，`scripts/ci/run_architecture_gates.sh` 与 CI 均强制 promtool 语义校验） |

## 依赖

- 主部署入口：[scripts/deploy.py](../scripts/deploy.py) · [scripts/_ARCH.md](../scripts/_ARCH.md)
