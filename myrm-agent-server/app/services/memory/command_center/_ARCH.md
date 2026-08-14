# services/memory/command_center 模块架构

## 架构概述

个人大脑指挥中心聚合服务与洞察服务。基于 MemoryManager、Shared Context ORM、待审批记忆、记忆操作账本、导入回滚账本健康、归档恢复账本健康、Memory Diagnostics 和部署设置生成单用户/单沙箱可观测快照，把账本中的检索步骤聚合为运行级 trace run；洞察层生成影响证据、注入成本/缓存、声明替代、会话回放覆盖层、replay event trail、瀑布流、eval checks、连接器状态、隐私信号等。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `command_center.py` | 核心 | 个人大脑指挥中心聚合服务。基于 MemoryManager、Shared Context ORM、待审批记忆、记忆操作账本、导入回滚账本健康、归档恢复账本健康、Memory Diagnostics 和部署设置生成单用户/单沙箱可观测快照，把账本中的检索步骤聚合为运行级 trace run，支持强制刷新健康快照，并支持可选 `project_id` 参数将快照聚焦到单个项目绑定的 SharedContext 记忆空间；runtime 状态含 `vector_persistence`（persistent/memory_fallback/unavailable）揭示向量层真实持久性 | ✅ |
| `command_center_insights.py` | 核心 | 个人大脑指挥中心洞察服务。生成影响证据、注入成本/缓存、声明替代、会话回放覆盖层、replay event trail、瀑布流、eval checks、连接器状态、隐私信号、含导入回滚与归档恢复健康的部署边界摘要、迁移来源聚合（含 source_manifest authoritative 完整性降级守卫）、最近导入批次、导入后验证建议、自动诊断状态和导入审查清理指标 | ✅ |
| `command_center_projection_utils.py` | 辅助 | 个人大脑指挥中心投影辅助。集中维护阶段映射、瀑布流状态、预览、数值解析和 eval metric 构建，避免洞察服务膨胀 | ✅ |
