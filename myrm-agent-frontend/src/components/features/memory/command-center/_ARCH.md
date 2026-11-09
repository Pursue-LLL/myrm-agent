# memory/command-center/

## 架构概述

记忆命令中心：诊断、修复与高级编排的统一入口。门面负责面板编排，子面板按职责拆分，避免单文件承载全部诊断逻辑。

设置页 **Memory Command Center** 整体默认隐藏；本地/开发需 `NEXT_PUBLIC_MEMORY_LABS=1` 并重启 WebUI，且服务端 `MYRM_MEMORY_LABS=1`（见 `MemorySection.tsx`、`memoryLabs.ts`）。Two-layer studio 卡片同样受 labs 开关约束（见 `MemoryCommandCenterUnderstandSection.tsx`）。

## 文件清单

| 文件                                    | 地位 | 职责                                                             | I/O/P |
| --------------------------------------- | ---- | ---------------------------------------------------------------- | ----- |
| `MemoryCommandCenter.tsx`               | 门面 | 命令中心主布局：数据装配、面板编排与跨面板状态协调               | ✅    |
| `MemoryCommandCenterPanels.tsx`         | 核心 | 主内容区观察/治理/验证分区面板编排（概览/召回/健康等基础面板）   | ✅    |
| `MemoryCommandCenterUnderstandSection.tsx` | 核心 | 「理解」分区：记忆经济学、行为指标、记忆能力卡片挂载与影响/冲突面板；Two-layer studio 卡片受 labs 开关约束 | ✅    |
| `MemoryCommandCenterObservationPanels.tsx` | 辅助 | 只读观测子面板：记忆影响行、实时事件流、运行时状态、成本与回放概览 | ✅    |
| `MemoryCommandCenterGovernancePanels.tsx` | 辅助 | 治理子面板：治理动作行、迁移覆盖与适配器状态面板、自动整理撤销卡片 | ✅    |
| `MemoryCommandCenterPrimitives.tsx`     | 辅助 | 分区面板共用原子组件：版块、指标块、运行时行与空态               | ✅    |
| `memoryCommandCenterFormat.ts`          | 辅助 | 分区面板共用枚举守卫与文案格式化（memory 命名空间翻译、时间与事件描述） | ✅    |
| `MemoryCommandCenterAdvancedPanels.tsx` | 核心 | 高级面板集合（容量剧场、偏好雷达、检索诊断等进阶视图）           | ✅    |
| `MemoryCommandCenterDoctorPanel.tsx`    | 核心 | 记忆医生面板：诊断项与可执行诊断入口                       | ✅    |
| `MemoryDoctorRunSection.tsx`            | 组件 | 单次诊断运行视图：运行摘要、benchmark 指标、探针结果与 probe 级修复计划| ✅    |
| `MemoryDoctorTrend.tsx`                 | 组件 | 诊断历史趋势：recall / ndcg / mrr / 延迟走势、较上次变化与类别通过率| ✅    |
| `MemoryDoctorStatusPill.tsx`            | 组件 | 就绪度状态徽章，趋势区、运行摘要与检查项共用                   | ✅    |
| `memoryDoctorModel.ts`                  | 辅助 | 医生面板共用的动作联合类型、取值守卫与展示格式化                 | ✅    |
| `MemoryCommandCenterChrome.tsx`         | 辅助 | 命令中心外壳（标题、工具栏、tab 切换与操作区）                   | ✅    |
| `MemoryRecallBoundaryPanel.tsx`         | 辅助 | 召回边界面板：读取范围、候选待审池、四职责分区的真实记忆数量与已生效记忆样本 | ✅    |
| `CognitiveClockPanel.tsx`               | 核心 | 多频认知时钟状态面板：T0-T3 状态指示、前台打字让步指示与手动提炼 | ✅    |
| `MemoryEconomicsPanel.tsx`              | 核心 | 长程有状态任务记忆经济学剖析面板：三阶段开销、ROI 轨迹与沉睡治理 | ✅    |
| `MemoryEconomicsKpiCards.tsx`           | 辅助 | 经济学面板指标卡片子组件：三阶段时延细分、前缀缓存保持率与 ROI   | ✅    |
| `MemoryParasiticGovernanceList.tsx`     | 辅助 | 经济学面板沉睡治理子组件：低效沉睡记忆列表、单条与批量归档操作   | ✅    |
| `FirstEncounterReportCard.tsx` | 核心 | 历史会话轻量采样与“初见报告”冷启动卡片：多源 Agent 探测雷达、首2尾12关键帧采样、香农熵双轨零泄漏脱敏与个人技术画像一键入库 | ✅    |
| `PrivateNotebookCard.tsx` | 核心 | 透明可检视模型私有笔记本卡片：Notes 5 工具操作台、历史交互检索与平滑跨窗口接力 | ✅    |
| `PrivateNotebookNotesListView.tsx` | 辅助 | 私有笔记本卡片子组件：呈现透明 Markdown 笔记索引、行数统计、实时检视与人工纠偏覆写 | ✅    |
| `PrivateNotebookHistoryView.tsx` | 辅助 | 私有笔记本卡片子组件：跨上下文窗口长程交互历史检索、归档窗口列表与流式条目展现 | ✅    |
| `PrivateNotebookHandoverView.tsx` | 辅助 | 私有笔记本卡片子组件：跨窗口平滑移交 (new_context) 表单、交接原因录入与状态报告 | ✅    |
| `PromptCachePreservingDeltaCard.tsx` | 核心 | 会话内记忆更新检视：稳定 system 前缀 + human 尾部的布局预览；默认绑定当前聊天 session；命中率见聊天上下文环，此处不展示伪造百分比 | ✅    |
| `EphemeralDeltaLiveInspectorView.tsx` | 辅助 | 瞬态增量实时检视子组件：呈现活跃增量列表、交互式用户修正录入表单、LWW 重写覆盖与前缀哈希校验 | ✅    |
| `PromptCacheConsolidationView.tsx` | 辅助 | 缓存一致性与归档子组件：双轨预览、一键归档落库；HUD 仅展示后端遥测，无数据时显示占位符 | ✅    |
| `TwoLayerDialecticStudioCard.tsx` | 核心 | Lab-only（`NEXT_PUBLIC_MEMORY_LABS=1`）两层上下文布局预览：Layer 1 用户消息尾快照、Layer 2 辩证调和控制台；只经 `/memory/two-layer-dialectic/*` 预览，不进入任何对话轮次，命中率见聊天上下文环 | ✅    |
| `TwoLayerDialecticHudBar.tsx` | 辅助 | 两层辩证 4 维 HUD：前缀布局稳定提示、Layer 1/2 周期与辩证深度；不展示伪造缓存命中率 | ✅    |
| `BaseContextCacheView.tsx` | 辅助 | Layer 1 基础上下文与 Prompt Cache 检视子组件：呈现冻结 System 块、User 尾部注入块、持久 Cache Key 与单次编译仿真 | ✅    |
| `DialecticReconciliationConsoleView.tsx` | 辅助 | Layer 2 自适应辩证推理工作台子组件：支持配置矛盾事实并启动 1~3 遍正题/反题/合题辩证调和，展示置信度与合成事实 | ✅    |
| `DialecticCadenceControlsView.tsx` | 辅助 | 双层实验室：Layer 1/2 周期、辩证深度与 reasoning 等级调优（i18n；不承诺缓存命中率） | ✅    |
| `twoLayerDialecticFallbacks.ts` | 辅助 | 两层上下文解耦与辩证推理调和离线及单测仿真数据集 | ✅    |

## 依赖



- `@/services/memory`、`@/store/*`、`@/components/primitives/*`
- 兄弟子目录 `../cards/`、`../dialogs/`、`../hooks/`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
