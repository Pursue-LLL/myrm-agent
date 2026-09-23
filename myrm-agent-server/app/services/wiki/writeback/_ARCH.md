# services/wiki/writeback 模块架构

## 架构概述

提供生产级任务使用台账（Usage Ledger）与作者审阅单（Review Slip）选择性回写引擎。
彻底解决长程任务交付后“全量回写污染知识库、完全不回写丢失经验”的两难困境。

## 核心职责

1. **Usage Ledger（使用台账）**：
   - 追踪记录单次任务交付中所引用的知识页、生成的交付物以及未采用条目；
   - 存储于 `{vault_path}/deliverables/ledgers/{task_id}.json`。
2. **Negative Exclusion Guard（负向不回写硬拦截）**：
   - 基于 Harness `NegativeExclusionPolicy`，拦截 5 类单次瞬态数据（讲师逐字稿、特定环境IP/VPC、虚拟样本数据、临时崩溃日志、定制客户报价）。
3. **Review Slip（作者审阅单）**：
   - 将通过过滤的有效洞察聚合提炼为 1~5 道极简单选题决策卡；
   - 支持单键将经验归档至 `knowledge/methods/` 或 `knowledge/claims/`（保持 `draft` 状态）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `schemas.py` | 契约 | Pydantic DTO 定义（台账记录、审阅单问题、提交回写请求） | ✅ |
| `service.py` | 核心 | `WikiWritebackService` 单机核心服务 | ✅ |
| `__init__.py` | 入口 | 模块门面统一导出 | ✅ |
