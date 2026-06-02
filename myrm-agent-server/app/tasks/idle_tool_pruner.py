"""
[INPUT]
- app.services.approvals.registry::ApprovalRegistry (POS: 统一的拦截审批注册与唤醒中枢)
- myrm_agent_harness.agent.tool_management.action_space::ActionSpaceProfiler (POS: 动作空间量化引擎)

[OUTPUT]
- scan_and_prune_idle_tools: 自动扫描闲置工具并生成净化审批流

[POS]
自动清理管家后台任务。负责扫描长期未使用但占据大模型前缀空间的高负载工具，转换为用户可视的清理提案。

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

import logging

# TODO: Fix import - SkillStore class has been moved or renamed
# from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore

logger = logging.getLogger(__name__)

async def scan_and_prune_idle_tools() -> int:
    """
    扫描长期闲置的工具并生成净化审批任务。
    
    1. 遍历所有自定义 Agent 配置。
    2. 对于每个 Agent，提取其启用的 Core Skills。
    3. 查询其使用状态（usage_stats.lifecycle_status），找出被标记为 'stale'（闲置）的工具。
    4. 若这些闲置工具影响了决策准确率，则向 ApprovalRegistry 提交一条 ActionType 为 `idle_tool_prune` 的审批记录。
       
    Returns:
        生成的净化提案数量
    """
    logger.info("Starting idle tool scanning for Action Space optimization...")
    logger.warning("Idle tool pruning is temporarily disabled due to SkillStore import issue")
    
    # TODO: Re-enable this functionality after fixing SkillStore import
    return 0
    
    # proposals_created = 0
    # 
    # try:
    #     # 获取数据库会话
    #     async for db in get_db():
    #         # 查找所有活跃的 Agent
    #         result = await db.execute(select(Agent).where(Agent.is_active == True))
    #         agents = result.scalars().all()
    #         
    #         for agent in agents:
    #             idle_skills = []
    #             
    #             # 检查已启用的技能
    #             if isinstance(agent.skill_ids, list):
    #                 for skill_id in agent.skill_ids:
    #                     skill = await SkillStore.get_skill_by_id(skill_id)
    #                     if skill and skill.usage_stats:
    #                         # 判断是否为闲置状态
    #                         if skill.usage_stats.get("lifecycle_status") == "stale":
    #                             idle_skills.append({"id": skill.id, "name": skill.name})
    #             
    #             # 如果发现闲置技能，则抛出审批流
    #             if idle_skills:
    #                 # 去重，避免重复抛出相同的审批
    #                 # 在实际业务中可能需要查 ApprovalRecord 表确认是否已有 pending 审批
    #                 skill_names = ", ".join([s["name"] for s in idle_skills])
    #                 
    #                 await ApprovalRegistry.create_approval(
    #                     agent_id=agent.id,
    #                     action_type="idle_tool_prune",
    #                     reason=f"管家发现 {len(idle_skills)} 个沉睡技能（{skill_names}）已连续 30 天未被调用。它们正在拉低 15% 的决策准确度，建议一键卸载以净化动作空间。",
    #                     severity="warning",
    #                     payload={"prune_skills": [s["id"] for s in idle_skills]},
    #                 )
    #                 proposals_created += 1
    # 
    # except Exception as e:
    #     logger.error(f"Failed to scan idle tools: {e}")
    # 
    # logger.info(f"Idle tool scanning completed: {proposals_created} proposals generated")
    # return proposals_created

