# services/memory/shared_context 模块架构

## 架构概述

Shared Context 共享上下文的产品层治理。管理上下文 CRUD、绑定解析、写入提案生命周期（goal_completion / correction_propagation 幂等 dedup）及治理 policy；记忆健康服务安全检查 embedding 配置并支持实时探测；历史证据服务构建历史消息提升提案的来源元数据；写入物化服务批准 proposal 后幂等写入目标 shared namespace 并附加审计元数据。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `shared_context.py` | 核心 | Shared Context 共享上下文服务。管理上下文 CRUD、绑定解析、写入提案生命周期（goal_completion / correction_propagation 幂等 dedup）及治理 policy | ✅ |
| `shared_context_health.py` | 核心 | Shared Context 记忆健康服务。安全检查 embedding 配置并支持实时探测，供 UI、API 和 smoke 验证复用 | ✅ |
| `shared_context_history.py` | 核心 | Shared Context 历史证据服务。复用会话历史搜索并构建历史消息提升提案的来源元数据 | ✅ |
| `shared_context_materializer.py` | 核心 | Shared Context 写入物化服务。批准 proposal 后幂等写入目标 shared namespace，并附加审计元数据 | ✅ |
