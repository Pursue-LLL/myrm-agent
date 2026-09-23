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
3. **Review Slip 与 Provenance 溯源凭证注入**：
   - 将通过过滤的有效洞察聚合提炼为 1~5 道极简单选题决策卡；
   - 支持单键将经验归档至 `knowledge/methods/` 或 `knowledge/claims/`（保持 `draft` 状态），并在 YAML frontmatter 中规范注入 `evidence` 凭证链（`source_task_id`, `source_deliverable`, `negative_exclusion_verified: true`）。
4. **Layer Items Inspection（五层资产微观下钻）**：
   - 按分层（L1-L5）提供轻量级文档清单与 Markdown/JSON 摘要检索；
   - L5 交付物层同时支持穿透扫描与安全解析 `deliverables/ledgers/*.json` 机器审计台账；
   - 完整提取并透传 `source_task_id` 溯源凭证与 `file_type`，支持前端卡片徽标展示与单键在 Wiki 编辑器中打开。


## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `schemas.py` | 契约 | Pydantic DTO 定义（台账记录、审阅单问题、提交回写请求、`WikiLayerItem`） | ✅ |
| `service.py` | 核心 | `WikiWritebackService` 单机核心服务（台账管理、回写执行、分层文档列表） | ✅ |
| `__init__.py` | 入口 | 模块门面统一导出 | ✅ |
