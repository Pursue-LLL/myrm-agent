# services/memory/command_center 模块架构

## 架构概述

个人大脑指挥中心聚合服务与洞察服务。基于 MemoryManager、Shared Context ORM、待审批记忆、记忆操作账本、导入回滚账本健康、归档恢复账本健康、Memory Diagnostics 和部署设置生成单用户/单沙箱可观测快照，把账本中的检索步骤聚合为运行级 trace run；洞察层生成影响证据、注入成本/缓存、声明替代、会话回放覆盖层、replay event trail、瀑布流、eval checks、连接器状态、隐私信号等。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `command_center.py` | 核心 | 个人大脑指挥中心聚合服务。基于 MemoryManager、Shared Context ORM、待审批记忆、记忆操作账本、导入回滚账本健康、归档恢复账本健康、Memory Diagnostics 和部署设置生成单用户/单沙箱可观测快照，把账本中的检索步骤聚合为运行级 trace run，支持强制刷新健康快照，支持按项目过滤空间，并提供 `build_recall_boundary_snapshot` 聚合审查优先召回边界（任务级 read_scopes、Candidate 候选池、四职责分区与 6000 字符装载预算）；runtime 状态含 `vector_persistence` 揭示持久性 | ✅ |
| `command_center_pending.py` | 核心 | 指挥中心读取待审内容的唯一入口：待审阅计数（审批队列 + 待裁决冲突）、候选列表、治理项（仅批准/拒绝，纠正/遗忘提案披露目标记忆）与时间线回退，全部读 harness 审批队列；ORM `pending_memories` 仅保留冲突待裁决行 | ✅ |
| `command_center_insights.py` | 核心 | 个人大脑指挥中心洞察服务。生成影响证据、注入成本/缓存、声明替代、会话回放覆盖层、replay event trail、瀑布流、eval checks、连接器状态、隐私信号、含导入回滚与归档恢复健康的部署边界摘要、迁移来源聚合（含 source_manifest authoritative 完整性降级守卫）、最近导入批次、导入后验证建议、自动诊断状态和导入审查清理指标 | ✅ |
| `command_center_economics.py` | 核心 | 长程任务记忆经济学分析服务。对标 Omri et al. (2026)，拆解构建/检索/注入三阶段开销，量化长程任务有效召回 ROI 与 Prompt Cache 保持率，支持模型自适应单价，识别沉睡低效记忆池并联动一键归档与置顶保护免杀 | ✅ |
| `command_center_projection_utils.py` | 辅助 | 个人大脑指挥中心投影辅助。集中维护阶段映射、瀑布流状态、预览、数值解析和 eval metric 构建，避免洞察服务膨胀 | ✅ |

