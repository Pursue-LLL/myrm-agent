# services/memory/score_honesty 模块架构

## 架构概述

检索评分诚实性与双门禁透明检验的业务服务适配层：包装 harness `RetrievalScoreHonestySuite`，将底层领域模型（`HonestScoredCandidate`、`ScoreBreakdown`、`DualThresholdConfig`、`ThresholdEvaluationVerdict`、`ScoreHonestyStats`）转换为 Server API DTO，并维护单进程单例 provider。核心算法与执行逻辑全部在 harness 引擎，本目录仅负责 DTO 适配与单例状态管理。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `provider.py` | 核心 | `ScoreHonestyProvider`：持有 harness suite，执行 candidate 创建、双阈值评估、过滤及 DTO 转换 | — |
| `__init__.py` | 入口 | 导出 `ScoreHonestyProvider` 与单例获取函数 `get_score_honesty_provider` | — |

## 模块依赖

- 上游：`myrm_agent_harness.toolkits.memory.score_honesty`（执行引擎）、`app.schemas.score_honesty`（API DTO）
- 下游：`app/api/memory/score_honesty_router.py`
