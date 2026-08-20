"""Kanban task skill-id validation helper.

[INPUT]
app.core.skills.store.service::skills_service (POS: 技能全集查询)
fastapi::HTTPException (POS: 框架 HTTP 异常)

[OUTPUT]
validate_extra_skill_ids: 校验任务技能 id 均存在于可发现技能集，非法即 400

[POS]
Kanban Task 路由辅助层。承载 extra_skill_ids 存在性校验，供 create/update 端点复用。
"""

from __future__ import annotations

from fastapi import HTTPException

from app.core.skills.store.service import skills_service


async def validate_extra_skill_ids(extra_skill_ids: list[str]) -> None:
    """Reject task skill ids that do not exist in the discoverable skill set.

    User-facing guard on the create/update path only. Internal task creation
    bypasses this check and is safe by construction: decompose/specify do not
    emit skill ids today (``DecomposeChildSpec.extra_skill_ids`` stays empty),
    and pipeline instantiation only injects template-defined skills.
    """
    if not extra_skill_ids:
        return
    skills = await skills_service.list_skills(skill_type=None)
    known_ids = {skill.id for skill in skills}
    unknown_ids = sorted({sid for sid in extra_skill_ids if sid not in known_ids})
    if unknown_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown skill id(s): {', '.join(unknown_ids)}. Available skills: {', '.join(sorted(known_ids)) or '(none)'}."
            ),
        )
