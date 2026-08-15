"""批量导入 (GUI-First 技能迁移) 接口的请求/响应模型。

[INPUT]
- batch_import（路由层）: preview/confirm 端点使用这些模型定义请求与响应结构

[OUTPUT]
- ImportPreviewSkillItem / ImportPreviewResponse: preview 端点响应模型
- ConfirmImportItem / ConfirmImportRequest / ConfirmImportResponse: confirm 端点请求/响应模型

[POS]
Schemas 与路由拆分，batch_import.py 保持聚焦业务编排与安全防护。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ImportPreviewSkillItem(BaseModel):
    name: str
    description: str
    conflict_type: Literal["none", "conflict"]
    existing_skill_id: str | None = None
    # 将 ZIP 中的相对路径作为内部索引
    virtual_id: str
    # 前置安全扫描结果
    security_issues: str | None = None


class ImportPreviewResponse(BaseModel):
    session_id: str
    items: list[ImportPreviewSkillItem]
    total_found: int
    total_conflicts: int


class ConfirmImportItem(BaseModel):
    virtual_id: str
    name: str
    description: str
    resolution: Literal["replace", "rename_cow", "skip", "new"]
    existing_skill_id: str | None = None


class ConfirmImportRequest(BaseModel):
    session_id: str
    items: list[ConfirmImportItem]


class ConfirmImportResponse(BaseModel):
    imported_count: int
    skipped_count: int
    # 导入后保留的回归门禁用例总数（跨全部导入技能累计）：
    # 包内 evals.json 还原 + replace 场景从 DB 继承
    restored_eval_cases: int = 0
