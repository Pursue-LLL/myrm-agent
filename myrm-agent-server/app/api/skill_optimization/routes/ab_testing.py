from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.skill_optimization import (
    ABTestRepository,
)
from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.api.skill_optimization.dependencies import (
    get_ab_test_manager,
    get_storage,
)
from app.database.connection import get_db
from app.services.skill_optimization.ab_test_manager import ABTestManager

router = APIRouter()

@router.get("/ab-tests")
async def list_ab_tests(db: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    """获取A/B测试列表"""
    ab_repo = ABTestRepository(db)
    tests = await ab_repo.get_running_tests()

    return [
        {
            "id": test.id,
            "skill_id": test.skill_id,
            "status": test.status,
            "sample_size": test.sample_size,
            "baseline_version": test.baseline_version,
            "candidate_version": test.candidate_version,
            "candidate_score": test.candidate_score,
            "started_at": test.started_at.isoformat(),
        }
        for test in tests
    ]

class ABTestStartRequest(BaseModel):
    """A/B测试启动请求"""

    skill_id: str
    baseline_version: int
    candidate_content: str

@router.post("/ab-tests/start")
async def start_ab_test(
    request: ABTestStartRequest,
    storage: Annotated[SQLAlchemyStorage, Depends(get_storage)],
) -> dict[str, object]:
    """启动A/B测试"""
    from myrm_agent_harness.agent.skills.optimization import ABTestEngine
    from myrm_agent_harness.agent.skills.optimization.config import ABTestConfig

    # 获取基线版本的质量评分
    baseline_skill_version = await storage.get_skill_version(
        request.skill_id,
        request.baseline_version,
    )

    if not baseline_skill_version or not baseline_skill_version.quality_score:
        raise HTTPException(
            status_code=404,
            detail=f"Baseline version {request.baseline_version} not found or has no quality score",
        )

    # 创建A/B测试引擎
    ab_engine = ABTestEngine(ABTestConfig())

    # 启动测试
    test_result = await ab_engine.start_ab_test(
        skill_id=request.skill_id,
        baseline_version=request.baseline_version,
        baseline_score=baseline_skill_version.quality_score,
        candidate_content=request.candidate_content,
    )

    # 保存测试结果到storage
    await storage.save_ab_test(test_result)

    return {
        "test_id": f"{request.skill_id}:v{request.baseline_version}",
        "skill_id": test_result.skill_id,
        "baseline_version": test_result.baseline_version,
        "candidate_version": test_result.candidate_version,
        "status": test_result.status.value,
        "sample_size": test_result.sample_size,
        "started_at": test_result.started_at.isoformat(),
    }

@router.get("/ab-tests/{skill_id}/status")
async def get_ab_test_status(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    include_samples: bool = False,
) -> dict[str, object]:
    """获取A/B测试进度及其样本"""
    ab_repo = ABTestRepository(db)
    tests = await ab_repo.get_running_tests()
    test = next((t for t in tests if t.skill_id == skill_id), None)

    if not test:
        raise HTTPException(status_code=404, detail=f"No running AB test for skill {skill_id}")

    samples = []
    if include_samples:
        samples_models = await ab_repo.get_samples(test.id, limit=10)
        samples = [
            {
                "id": s.id,
                "inputs": s.inputs,
                "baseline_output": s.baseline_output,
                "candidate_output": s.candidate_output,
                "is_match": s.is_match,
                "similarity_score": s.similarity_score,
                "baseline_latency_ms": s.baseline_latency_ms,
                "candidate_latency_ms": s.candidate_latency_ms,
                "diff_summary": s.diff_summary,
                "recorded_at": s.recorded_at.isoformat(),
            }
            for s in samples_models
        ]

    from myrm_agent_harness.agent.skills.optimization.config import ABTestConfig

    ab_config = ABTestConfig()

    return {
        "id": test.id,
        "skill_id": test.skill_id,
        "status": test.status,
        "baseline_version": test.baseline_version,
        "candidate_version": test.candidate_version,
        "sample_size_current": test.sample_size,
        "sample_size_target": ab_config.max_sample_size,
        "candidate_score": test.candidate_score,
        "started_at": test.started_at.isoformat(),
        "samples": samples,
    }

@router.post("/ab-tests/{skill_id}/promote")
async def promote_skill_version(
    skill_id: str,
    version: int,
    manager: Annotated[ABTestManager, Depends(get_ab_test_manager)],
) -> dict[str, str | int]:
    """提升某个版本为正式版本并关闭 A/B 测试"""
    success = await manager.promote_version(skill_id, version)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to promote version")

    return {"status": "success", "promoted_version": version}

@router.post("/ab-tests/{skill_id}/stop")
async def stop_ab_test(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """提前停止A/B测试，保持 baseline 版本不变。"""
    ab_repo = ABTestRepository(db)
    running_tests = await ab_repo.get_running_tests()
    test = next((t for t in running_tests if t.skill_id == skill_id), None)

    if not test:
        raise HTTPException(
            status_code=404,
            detail=f"No running A/B test found for skill {skill_id}",
        )

    score = test.candidate_score or {}
    success_rate = score.get("success_rate", 0.0)

    winner = "candidate" if success_rate >= 0.95 else "baseline"
    status = "CANDIDATE_WIN" if winner == "candidate" else "STOPPED"

    await ab_repo.update_status(
        test_id=test.id,
        status=status,
        winner=winner,
    )

    return {
        "test_id": test.id,
        "skill_id": skill_id,
        "status": status,
        "winner": winner,
        "baseline_version": test.baseline_version,
        "candidate_version": test.candidate_version,
        "candidate_score": score,
        "sample_size": test.sample_size,
    }

