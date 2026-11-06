# llms/routing/complexity_router/

## 架构概述

复杂度路由：关键词与提示、类型、信号、评分、动量、LLM judge、去重与入口分层；`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 聚合导出 route_task / 类型 / 关键词 / 评分与缓存 |
| `keywords.py` | 默认关键词、简单指示词、judge 系统提示 |
| `types.py` | RoutingTier / RoutingResult / WeightedKeyword |
| `signals.py` | 结构/上下文信号、查询归一化、文本特征 |
| `scoring.py` | 统一评分、阈值与规则分类 |
| `momentum.py` | 会话动量调整 |
| `judge.py` | LLM judge 缓存与模型选择 |
| `dedup.py` | 路由结果去重缓存 |
| `route.py` | `route_task` 入口 |
