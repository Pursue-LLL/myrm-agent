# services/memory/command_center 模块架构

## 架构概述

个人大脑指挥中心聚合服务与洞察服务。基于 MemoryManager、Shared Context ORM、待审批记忆、记忆操作账本、导入回滚账本健康、归档恢复账本健康、Memory Diagnostics 和部署设置生成单用户/单沙箱可观测快照，把账本中的检索步骤聚合为运行级 trace run；洞察层生成影响证据、注入成本/缓存、声明替代、会话回放覆盖层、replay event trail、瀑布流、eval checks、连接器状态、隐私信号等；各投影位于独立模块，聚合服务只负责编排。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `command_center.py` | 核心 | 个人大脑指挥中心聚合服务，只做编排：生成单用户/单沙箱可观测快照，支持强制刷新健康快照、按项目过滤空间/治理，并提供 `build_recall_boundary_snapshot` 委托召回边界模块；runtime 状态含 `vector_persistence` 揭示持久性；对外保留 `get_archived_memory_ids/get_pinned_memory_ids/get_active_memory_previews` 三个读取入口 | ✅ |
| `command_center_memory_scan.py` | 核心 | 指挥中心对 MemoryManager 的只读扫描层：`ALL_MEMORY_TYPES` 枚举、按类型计数、归档/置顶 ID 与活跃记忆预览收集，单类型失败只记日志不影响整体快照 | ✅ |
| `command_center_health.py` | 核心 | 健康快照：5 分钟 TTL 缓存读取、强制刷新时计算分数并写入账本与操作事件，分数到状态的映射 | ✅ |
| `command_center_timeline.py` | 核心 | 时间线投影：优先读操作账本（按项目收窄命名空间），账本为空时回退为待审/共享提案/共享上下文事件 | ✅ |
| `command_center_trace.py` | 核心 | 把账本中的检索步骤事件按 trace_id 聚合为运行级 trace run（步骤排序、状态汇总、耗时） | ✅ |
| `command_center_replay.py` | 核心 | 回放覆盖层、replay event trail 与记忆生命周期瀑布流的纯函数投影 | ✅ |
| `command_center_influence.py` | 核心 | 从近期助手消息的 `citedMemoryRefs` 与 token 统计构建影响证据条目 | ✅ |
| `command_center_recall_boundary.py` | 核心 | 审查优先召回边界：任务级 read_scopes、Candidate 候选池、四职责分区统计与 6000 字符装载预算 | ✅ |
| `command_center_pending.py` | 核心 | 指挥中心读取待审内容的唯一入口：待审阅计数（审批队列 + 待裁决冲突）、候选列表、治理项（仅批准/拒绝，纠正/遗忘提案披露目标记忆）与时间线回退，全部读 harness 审批队列；ORM `pending_memories` 仅保留冲突待裁决行 | ✅ |
| `command_center_insights.py` | 核心 | 个人大脑指挥中心洞察服务。生成冲突/纠正/声明、eval checks、连接器状态、隐私信号、含导入回滚与归档恢复健康的部署边界摘要、迁移来源聚合（含 source_manifest authoritative 完整性降级守卫）、最近导入批次、导入后验证建议、自动诊断状态和导入审查清理指标；影响证据委托 `command_center_influence` | ✅ |
| `command_center_economics.py` | 核心 | 长程任务记忆经济学分析服务。对标 Omri et al. (2026)，拆解构建/检索/注入三阶段开销，量化长程任务有效召回 ROI 与 Prompt Cache 保持率，支持模型自适应单价，识别沉睡低效记忆池并联动一键归档与置顶保护免杀 | ✅ |
| `command_center_projection_utils.py` | 辅助 | 个人大脑指挥中心投影辅助。集中维护阶段映射、瀑布流状态、预览、数值解析、per-turn 记忆遥测解析（`read_memory_telemetry`）、按项目收窄 SharedContext 查询（`restrict_to_context_ids`）和 eval metric 构建 | ✅ |

