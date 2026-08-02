"""Companion doctor HTTP routes (no feature gate).

[INPUT]
- app.services.companion.pet_doctor (POS: diagnostic orchestration)

[OUTPUT]
- GET /companion/doctor: read-only health report for GUI troubleshooting

[POS]
Ungated companion diagnostics so users can see why companion_mode/sprite setup fails.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class DoctorCheckResponse(BaseModel):
    id: str
    status: str
    message: str
    fix_action: str | None = None


class CompanionDoctorResponse(BaseModel):
    ready: bool
    checks: list[DoctorCheckResponse]
    active_slug: str | None = None
    installed_count: int = 0


@router.get("/doctor", response_model=CompanionDoctorResponse)
async def get_companion_doctor(rescan: bool = False) -> CompanionDoctorResponse:
    from app.services.companion.pet_doctor import run_companion_doctor

    report = await run_companion_doctor(rescan=rescan)
    return CompanionDoctorResponse(
        ready=report.ready,
        checks=[
            DoctorCheckResponse(
                id=check.id,
                status=check.status.value,
                message=check.message,
                fix_action=check.fix_action,
            )
            for check in report.checks
        ],
        active_slug=report.active_slug,
        installed_count=report.installed_count,
    )
