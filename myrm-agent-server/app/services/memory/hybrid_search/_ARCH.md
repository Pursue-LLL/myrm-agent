# services/memory/hybrid_search 模块架构

## 架构概述

双引擎混合检索：`DualEngineHybridSearchService` 编排 FTS 与向量双通道检索、多因子重排、自适应熔断器状态（`AdaptiveCircuitBreaker`）与降级回退，并转换为 `app.schemas.hybrid_search` DTO。检索通道通过 `set_providers` 注入；未注入时使用内存示例通道 `_default_mock_fts` / `_default_mock_vector`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 辅助 | 导出 `DualEngineHybridSearchService` 与 `get_hybrid_search_service` | ✅ |
| `provider.py` | 核心 | `DualEngineHybridSearchService`：search / get_circuit_status / reset_circuit_breaker / set_providers；`get_hybrid_search_service` 单例入口 | ✅ |
