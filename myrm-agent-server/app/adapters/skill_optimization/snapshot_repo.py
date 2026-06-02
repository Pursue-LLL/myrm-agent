"""Skill Version Repository

1. 本文件的 INPUT/OUTPUT/POS 注释
2. 所属文件夹的 _ARCH.md

[INPUT]
- sqlalchemy (POS: Python ORM框架)
- AsyncSession (POS: SQLAlchemy异步会话)
- SkillVersionModel (POS: Skill版本ORM模型)

[OUTPUT]
- SnapshotRepository: Skill版本CRUD操作类

[POS]
实现skill_versions表的CRUD操作，支持版本创建、查询、激活和删除。
管理skill的版本快照，支持版本回滚和对比。
"""

from __future__ import annotations

import logging
from datetime import datetime

from myrm_agent_harness.agent.skills.optimization.types import (
    SkillQualityScore,
    SkillVersion,
)
from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.skill_optimization import SkillVersionModel

logger = logging.getLogger(__name__)


class SnapshotRepository:
    """Skill版本Repository

    管理skill的版本快照，支持版本创建、查询、激活和删除。
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_version(
        self,
        skill_id: str,
        version: int,
        content: str,
        quality_score: SkillQualityScore | None = None,
        created_by: str = "llm",
        optimization_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> SkillVersion:
        """保存skill版本

        Args:
            skill_id: Skill ID
            version: 版本号
            content: Skill内容
            quality_score: 质量评分
            created_by: 创建者
            optimization_id: 关联的优化ID
            metadata: 额外元数据

        Returns:
            SkillVersion: 创建的版本对象
        """
        quality_score_dict = None
        if quality_score:
            quality_score_dict = {
                "success_rate": quality_score.success_rate,
                "token_efficiency": quality_score.token_efficiency,
                "execution_time": quality_score.execution_time,
                "user_satisfaction": quality_score.user_satisfaction,
                "call_frequency": quality_score.call_frequency,
                "prompt_tokens": quality_score.prompt_tokens,
                "completion_tokens": quality_score.completion_tokens,
                "total_tokens": quality_score.total_tokens,
                "llm_cost_usd": quality_score.llm_cost_usd,
            }

        model = SkillVersionModel(
            skill_id=skill_id,
            version=version,
            content=content,
            quality_score=quality_score_dict,
            created_at=datetime.utcnow(),
            created_by=created_by,
            optimization_id=optimization_id,
            is_active=False,
            extra_metadata=metadata,
        )

        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)

        logger.info(f"Saved skill version: {skill_id} v{version} (created_by={created_by}, optimization_id={optimization_id})")

        return self._model_to_domain(model)

    async def get_version(
        self,
        skill_id: str,
        version: int,
    ) -> SkillVersion | None:
        """获取指定版本

        Args:
            skill_id: Skill ID
            version: 版本号

        Returns:
            SkillVersion | None: 版本对象，不存在则返回None
        """
        result = await self.session.execute(
            select(SkillVersionModel).where(
                SkillVersionModel.skill_id == skill_id,
                SkillVersionModel.version == version,
            )
        )
        model = result.scalar_one_or_none()
        return self._model_to_domain(model) if model else None

    async def get_active_version(
        self,
        skill_id: str,
    ) -> SkillVersion | None:
        """获取当前激活版本

        Args:
            skill_id: Skill ID

        Returns:
            SkillVersion | None: 激活版本，不存在则返回None
        """
        result = await self.session.execute(
            select(SkillVersionModel).where(
                SkillVersionModel.skill_id == skill_id,
                SkillVersionModel.is_active == True,  # noqa: E712
            )
        )
        model = result.scalar_one_or_none()
        return self._model_to_domain(model) if model else None

    async def list_versions(
        self,
        skill_id: str,
        limit: int = 50,
    ) -> list[SkillVersion]:
        """列出skill的所有版本

        Args:
            skill_id: Skill ID
            limit: 返回数量限制

        Returns:
            list[SkillVersion]: 版本列表（按版本号倒序）
        """
        result = await self.session.execute(
            select(SkillVersionModel)
            .where(SkillVersionModel.skill_id == skill_id)
            .order_by(desc(SkillVersionModel.version))
            .limit(limit)
        )
        models = result.scalars().all()
        return [self._model_to_domain(model) for model in models]

    async def activate_version(
        self,
        skill_id: str,
        version: int,
    ) -> SkillVersion:
        """激活指定版本

        将指定版本标记为激活状态，并取消该skill其他版本的激活状态。
        操作顺序：先验证目标版本存在，再原子执行 deactivate + activate。

        Args:
            skill_id: Skill ID
            version: 版本号

        Returns:
            SkillVersion: 激活的版本对象

        Raises:
            ValueError: 版本不存在
        """
        # 1. 先验证目标版本存在（不修改任何数据）
        result = await self.session.execute(
            select(SkillVersionModel).where(
                SkillVersionModel.skill_id == skill_id,
                SkillVersionModel.version == version,
            )
        )
        model = result.scalar_one_or_none()

        if not model:
            raise ValueError(f"Version {version} not found for skill {skill_id}")

        # 2. 取消该skill所有版本的激活状态
        await self.session.execute(
            update(SkillVersionModel).where(SkillVersionModel.skill_id == skill_id).values(is_active=False)
        )

        # 3. 激活目标版本
        model.is_active = True
        await self.session.commit()
        await self.session.refresh(model)

        logger.info(f"Activated skill version: {skill_id} v{version}")

        return self._model_to_domain(model)

    async def delete_versions(
        self,
        skill_id: str,
        keep_latest: int = 10,
    ) -> int:
        """删除旧版本，保留最新的N个版本和激活版本

        Args:
            skill_id: Skill ID
            keep_latest: 保留的最新版本数量

        Returns:
            int: 删除的版本数量
        """
        result = await self.session.execute(
            select(SkillVersionModel).where(SkillVersionModel.skill_id == skill_id).order_by(desc(SkillVersionModel.version))
        )
        all_versions = list(result.scalars().all())

        if len(all_versions) <= keep_latest:
            return 0

        # 保留最新的 keep_latest 个版本 + 激活版本
        versions_to_keep = set(v.version for v in all_versions[:keep_latest])
        for v in all_versions:
            if v.is_active:
                versions_to_keep.add(v.version)

        versions_to_delete = [v for v in all_versions if v.version not in versions_to_keep]

        if not versions_to_delete:
            return 0

        delete_count = len(versions_to_delete)

        await self.session.execute(
            delete(SkillVersionModel).where(
                SkillVersionModel.skill_id == skill_id,
                SkillVersionModel.version.in_([v.version for v in versions_to_delete]),
            )
        )
        await self.session.commit()

        logger.info(f"Deleted {delete_count} old versions for skill {skill_id} (kept latest {keep_latest} + active)")

        return delete_count

    def _model_to_domain(self, model: SkillVersionModel) -> SkillVersion:
        """将ORM模型转换为领域对象

        Args:
            model: ORM模型

        Returns:
            SkillVersion: 领域对象
        """
        quality_score = None
        if model.quality_score:
            quality_score = SkillQualityScore(
                success_rate=model.quality_score["success_rate"],
                token_efficiency=model.quality_score["token_efficiency"],
                execution_time=model.quality_score["execution_time"],
                user_satisfaction=model.quality_score["user_satisfaction"],
                call_frequency=model.quality_score["call_frequency"],
                prompt_tokens=model.quality_score.get("prompt_tokens", 0),
                completion_tokens=model.quality_score.get("completion_tokens", 0),
                total_tokens=model.quality_score.get("total_tokens", 0),
                llm_cost_usd=model.quality_score.get("llm_cost_usd", 0.0),
            )

        return SkillVersion(
            skill_id=model.skill_id,
            version=model.version,
            content=model.content,
            quality_score=quality_score,
            created_at=model.created_at,
            created_by=model.created_by,
            optimization_id=model.optimization_id,
            is_active=model.is_active,
            metadata=model.extra_metadata,
        )
