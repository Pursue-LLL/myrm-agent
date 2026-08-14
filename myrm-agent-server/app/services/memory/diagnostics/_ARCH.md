# services/memory/diagnostics 模块架构

## 架构概述

独立 Memory Diagnostics 探针。生成 Memory Doctor 静态检查并执行 relational store、memory path、vector index、knowledge graph、embedding provider、embedding live、retrieval pipeline、sparse CJK recall、golden recall benchmark、memory quality governance、event ledger、migration integrity、health snapshot、deployment boundary 探针，写入不含业务内容的诊断审计事件；配套质量治理、黄金召回基准、修复计划与白名单执行、SLO 汇总和静态检查构建器。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `diagnostic_probe_results.py` | 辅助 | Memory Diagnostics probe 结果归一化。集中处理 rollup、action 状态映射、impact/next action/auto-fix/retry 字段、repair plan 传递和静态检查到可执行探针的转换 | ✅ |
| `diagnostic_quality_governance.py` | 辅助 | Memory Doctor 质量治理探针。读取框架层 health score，返回内容不可见的新鲜度、覆盖率、保留健康和一致性证据 | ✅ |
| `diagnostic_recall_benchmark.py` | 辅助 | Memory Doctor 黄金召回基准。16 个合成 case（8 类别 × 中英双语），写入 semantic/episodic 记忆、检索 top-5、清理探针数据，返回 recall@5/ndcg@5/mrr/precision@5/latency_p50/p95、per-category 命中统计和结构化 MemoryCommandBenchmarkSummary | ✅ |
| `diagnostic_repair_executor.py` | 核心 | Memory Doctor 修复执行器。通过白名单执行 `run_diagnostics`、`run_health_refresh`，对配置类修复返回 blocked/manual 结果，避免自动改本地配置或读取业务记忆内容 | ✅ |
| `diagnostic_repair_plans.py` | 辅助 | Memory Doctor 修复计划目录。把 compact action id 映射为风险等级、dry-run、预期效果和可执行性，不修改配置、不读取业务记忆内容 | ✅ |
| `diagnostic_slo.py` | 辅助 | Memory Doctor 诊断 SLO 汇总。读取最近诊断审计事件的 metadata，计算窗口通过率、失败次数和平均耗时 | ✅ |
| `diagnostic_static_checks.py` | 辅助 | Memory Doctor 静态检查构建器。生成 relational store、memory path、vector index、knowledge graph、embedding provider、event ledger、health snapshot、deployment boundary 快照检查；`probe_vector_index` 按向量持久性（persistent/memory_fallback/unavailable）输出状态、影响与修复指引 | ✅ |
| `diagnostics.py` | 核心 | Memory Diagnostics 服务。生成 Memory Doctor 静态检查并执行 relational store、memory path、vector index、knowledge graph、embedding provider、embedding live、retrieval pipeline、sparse CJK recall、golden recall benchmark、memory quality governance、event ledger、migration integrity、health snapshot、deployment boundary 探针，写入不含业务内容的诊断审计事件并返回审计写入状态与诊断 SLO；诊断审计事件将 benchmark 标量指标、类别通过率与 embedding 模型平铺进 ledger metadata 供历史趋势回归分析（含类别级退化定位与模型漂移提示）；retrieval pipeline 探针消费 `last_retrieval_trace.degraded`，降级时探针置 warning 并注明原因 | ✅ |
