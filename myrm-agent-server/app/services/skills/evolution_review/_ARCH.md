# services/skills/evolution_review 模块架构

## 架构概述

技能进化审核（evolution review）子模块。负责 evolution 审核生命周期：域类型定义、ApprovalRecord 持久化读写、创建与只读查询、审批/拒绝/修订/回滚动作，以及落盘编排与全量内容 apply + rollback。对外由 `../evolution_reviews.py` 门面 re-export。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.py` | 核心 | evolution 审核域类型与 ApprovalRecord 转换 | ✅ |
| `persistence.py` | 核心 | evolution ApprovalRecord 持久化读写（list/count 下推 SQL LIMIT + pending growth_status 过滤） | ✅ |
| `queries.py` | 核心 | 创建与只读查询（list/count 委托 persistence SQL） | ✅ |
| `actions.py` | 核心 | 审批 / 拒绝 / 修订 / 回滚 | ✅ |
| `disk.py` | 核心 | 落盘编排（description / shadow / approval 成功路径） | ✅ |
| `disk_content.py` | 核心 | 全量内容 apply + rollback（含 fork） | ✅ |
