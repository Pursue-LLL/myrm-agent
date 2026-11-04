# services/wiki/layers 模块架构

## 架构概述

提供五层资产（L1-L5）的分层文档清单。

## 核心职责

**Layer Items Inspection（五层资产微观下钻）**：
- 按分层（L1-L5）提供轻量级 Markdown 文档清单与摘要检索；
- 从 YAML frontmatter 取 `title` 与 `publish_status`，按修改时间倒序返回，支持前端卡片展示与单键在 Wiki 编辑器中打开。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `schemas.py` | 契约 | Pydantic DTO 定义（`WikiLayerItem`） | ✅ |
| `service.py` | 核心 | `WikiLayersService` 单机核心服务（分层文档列表） | ✅ |
| `__init__.py` | 入口 | 模块门面统一导出 | ✅ |
