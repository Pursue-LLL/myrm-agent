# services/memory/document_attachment 模块架构

## 架构概述

文档附件归属与回收清扫：维护 Harness `DocumentAttachmentSuite` 单例，并在 Harness 领域对象（`AttachmentOwnershipItem` / `MigrationLegacyEntry` / `MigrationReport` / `ReclaimAuditReport` / `AttachmentStats`）与 `app.schemas.document_attachment` DTO 之间转换，提供附件挂载、查询、解除、文档移除、回收清扫、旧数据迁移与统计。仅单用户沙箱。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 辅助 | 包标识 | ✅ |
| `provider.py` | 核心 | `get_document_attachment_suite` / `reset_document_attachment_suite` 单例；`execute_attach` / `query_document_attachments` / `query_attachment` / `execute_detach` / `execute_remove_document` / `execute_sweep` / `execute_migrate` / `get_attachment_stats` 业务入口 | ✅ |
