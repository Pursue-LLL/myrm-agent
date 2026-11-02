# services/memory/diagnostics 模块架构

## 架构概述

独立 Memory Diagnostics 探针。生成 Memory Doctor 静态检查并执行 relational store、memory path、vector index、knowledge graph、embedding provider、embedding live、retrieval pipeline、sparse CJK recall、golden recall benchmark、memory quality governance、event ledger、migration integrity、health snapshot、deployment boundary 探针，写入不含业务内容的诊断审计事件；配套质量治理、黄金召回基准、修复计划与白名单执行、SLO 汇总和静态检查构建器。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `diagnostic/`（子包） | 辅助 | Memory Doctor 诊断子域：`diagnostic_probe_results.py`（结果归一化）、`diagnostic_live_probes.py`（embedding live / retrieval pipeline / sparse CJK recall 运行期探针）、`diagnostic_migration_integrity.py`（迁移完整性检查）、`diagnostic_quality_governance.py`（质量治理探针）、`diagnostic_recall_benchmark.py`（黄金召回基准）、`diagnostic_repair_executor.py`（修复执行器）、`diagnostic_repair_plans.py`（修复计划目录）、`diagnostic_slo.py`（SLO 汇总）、`diagnostic_static_checks.py`（静态检查构建器）。`diagnostic/__init__.py` 为聚合门面 | ✅ |
| `diagnostics.py` | 核心 | Memory Diagnostics 服务（编排门面）。生成 Memory Doctor 静态检查并按顺序编排 relational store、memory path、vector index、knowledge graph、embedding provider、embedding live、retrieval pipeline、sparse CJK recall、golden recall benchmark、memory quality governance、event ledger、migration integrity、health snapshot、deployment boundary 探针（运行期探针与迁移检查的实现位于 `diagnostic/`；快照与运行共用同一份容量采样与关系型存储完整性检查），写入不含业务内容的诊断审计事件并返回审计写入状态与诊断 SLO；诊断审计事件将 benchmark 标量指标、类别通过率与 embedding 模型平铺进 ledger metadata 供历史趋势回归分析（含类别级退化定位与模型漂移提示） | ✅ |
