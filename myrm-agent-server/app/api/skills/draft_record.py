"""Skill growth draft record view.

[INPUT]
- datetime: 标准库时间类型

[OUTPUT]
- SkillDraftRecord: 审批记录展开后的草稿视图（类型、技能名、描述、触发条件、步骤、正文、评测用例与状态）

[POS]
技能草稿记录视图。路由层（drafts）从审批记录构造它，落地写入层（draft_materialize）只读取它，两者共享同一份数据形状而互不依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class SkillDraftRecord:
    id: str
    agent_id: str
    chat_id: str | None
    draft_type: str
    name: str | None
    description: str | None
    trigger_condition: str | None
    skill_steps: str | None
    content: str | None
    status: str
    reviewed_at: datetime | None
    created_at: datetime
    approval_status: str
    eval_cases: list[dict[str, object]] | None = None
