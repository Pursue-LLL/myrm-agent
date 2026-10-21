# analytics/

## 架构概述

生产力与可量化 ROI 分析服务包 (`AgentMeasurableRoiAndDailyTimeSavedHUD`, Item 51 P0)。
负责智能体自动化任务工时折算、算力 Token 成本核算、替代人工经济价值折算、ROI 乘数推导、高收益流程预置以及周度生产力里程碑摘要。

## 文件清单

| 文件名 | 类型 | 职责 | 状态 |
| :--- | :--- | :--- | :--- |
| `roi_service.py` | 服务 | 工时基准折算算法、Token 成本模型、投资回报率计算、高收益流程预制 | ✅ |
| `__init__.py` | 门面 | 导出 `RoiAnalyticsService` 及领域数据结构 | ✅ |

## 依赖关系

- 内部：`pydantic`
- 外部消费者：`app.api.system.roi_analytics_api`
