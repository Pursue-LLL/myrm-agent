# services/memory/diagnostics/diagnostic 子目录

## 架构概述

`diagnostic/` 是 Memory Doctor 诊断模块的**纯逻辑聚合子目录**：probe 构建、结果归一化、修复计划、质量治理与 SLO 汇总等无业务内容的检查逻辑都收在这里，由上层 `diagnostics.py`（`diagnostics/__init__.py`）统一编排为可执行的诊断探针序列。

## 文件清单

| 文件 | 类型 | 职责 | 状态 |
| --- | --- | --- | --- |
| `__init__.py` | 门面 | `diagnostic/` 子包入口，re-export 对外模块 | ✅ |
| `diagnostic_probe_results.py` | 辅助 | probe 结果归一化：rollup、action 状态映射、impact/next action/auto-fix/retry 字段、repair plan 传递、静态检查到可执行探针转换 | ✅ |
| `diagnostic_quality_governance.py` | 辅助 | 质量治理探针：读取框架层 health score，返回新鲜度/覆盖率/保留健康/一致性证据（不含内容） | ✅ |
| `diagnostic_recall_benchmark.py` | 辅助 | 黄金召回基准：18 个合成 case（9 类别 × 中英双语，含长文档 Head/Tail 深层穿透与分块折叠去重验证），返回 recall@5/ndcg@5/mrr/precision@5/duplicate_rate/distinct_sources 与 latency | ✅ |
| `diagnostic_repair_executor.py` | 核心 | 修复执行器：白名单执行 `run_diagnostics`/`run_health_refresh`/`restore_disciplined_defaults`，配置类修复返回 blocked/manual | ✅ |
| `diagnostic_repair_plans.py` | 辅助 | 修复计划目录：compact action id → 风险等级/dry-run/预期效果/可执行性（含 `restore_disciplined_defaults`） | ✅ |
| `diagnostic_slo.py` | 辅助 | 诊断 SLO 汇总：最近诊断审计事件窗口通过率、失败次数、平均耗时 | ✅ |
| `diagnostic_static_checks.py` | 辅助 | 静态检查构建器：relational store/memory path/vector index/knowledge graph/embedding provider/event ledger/health snapshot/deployment boundary 以及 capacity_theater 容量剧场与记忆纪律快照检查 | ✅ |

## 依赖边界

- 不修改本地配置，不读取业务记忆内容（探针只产出证据与修复指引）。
- 仅供 `diagnostics.py` 编排调用，禁止业务层直接依赖本子目录内部实现。
