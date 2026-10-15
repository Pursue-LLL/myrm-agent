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
| `MemoryCommandCenterGovernancePanels.tsx` | 辅助 | 治理子面板：治理动作行、迁移覆盖与适配器状态面板、整合回滚卡片 | ✅    |
| `MemoryCommandCenterPrimitives.tsx`     | 辅助 | 分区面板共用原子组件：版块、指标块、运行时行与空态               | ✅    |
| `memoryCommandCenterFormat.ts`          | 辅助 | 分区面板共用枚举守卫与文案格式化（memory 命名空间翻译、时间与事件描述） | ✅    |
| `MemoryCommandCenterAdvancedPanels.tsx` | 核心 | 高级面板集合（容量剧场、偏好雷达、检索诊断等进阶视图）           | ✅    |
| `MemoryCommandCenterDoctorPanel.tsx`    | 核心 | 记忆医生面板：诊断项、自动修复动作与修复结果趋势                 | ✅    |
| `MemoryCommandCenterChrome.tsx`         | 辅助 | 命令中心外壳（标题、工具栏、tab 切换与操作区）                   | ✅    |
| `MemoryRecallBoundaryPanel.tsx`         | 辅助 | 召回边界面板：注入预算与截断披露                                 | ✅    |
| `CognitiveClockPanel.tsx`               | 核心 | 多频认知时钟状态面板：T0-T3 状态指示、前台打字让步指示与手动提炼 | ✅    |
| `MemoryEconomicsPanel.tsx`              | 核心 | 长程有状态任务记忆经济学剖析面板：三阶段开销、ROI 轨迹与沉睡治理 | ✅    |
| `MemoryEconomicsKpiCards.tsx`           | 辅助 | 经济学面板指标卡片子组件：三阶段时延细分、前缀缓存保持率与 ROI   | ✅    |
| `MemoryParasiticGovernanceList.tsx`     | 辅助 | 经济学面板沉睡治理子组件：低效沉睡记忆列表、单条与批量归档操作   | ✅    |
| `SovereignMigrationInspectorCard.tsx`   | 核心 | 全量数字资产主权打包、跨机无损还原与多源迁入卡片：.myrmpkg 加密便携导出、路径解绑重映射与竞品智能体迁入 | ✅    |
| `CompetitorAssetDetectionView.tsx`      | 辅助 | 主权迁移卡片子组件：呈现本机第三方智能体资产（Hermes/Claude Code/Codex）嗅探结果与一键迁入 | ✅    |
| `ProjectLivingFactLedgerCard.tsx` | 核心 | 长期项目动态事实状态账本与四层上下文投影卡片：决议/否决/约束全景账本、4-Tier 动态投影仿真器与基于验证结果的能力沉淀飞轮 | ✅    |
| `FirstEncounterReportCard.tsx` | 核心 | 历史会话轻量采样与“初见报告”冷启动卡片：多源 Agent 探测雷达、首2尾12关键帧采样、香农熵双轨零泄漏脱敏与个人技术画像一键入库 | ✅    |
| `PrivateNotebookCard.tsx` | 核心 | 透明可检视模型私有笔记本卡片：对标 Codex PR #42385 超越版、Notes 5 工具操作台、历史交互检索与平滑跨窗口接力 | ✅    |
| `PrivateNotebookNotesListView.tsx` | 辅助 | 私有笔记本卡片子组件：呈现透明 Markdown 笔记索引、行数统计、实时检视与人工纠偏覆写 | ✅    |
| `PrivateNotebookHistoryView.tsx` | 辅助 | 私有笔记本卡片子组件：跨上下文窗口长程交互历史检索、归档窗口列表与流式条目展现 | ✅    |
| `PrivateNotebookHandoverView.tsx` | 辅助 | 私有笔记本卡片子组件：跨窗口平滑移交 (new_context) 表单、交接原因录入与状态报告 | ✅    |
| `PromptCachePreservingDeltaCard.tsx` | 核心 | 会话内记忆更新检视：稳定 system 前缀 + human 尾部的布局预览；默认绑定当前聊天 session；命中率见聊天上下文环，此处不展示伪造百分比 | ✅    |
| `EphemeralDeltaLiveInspectorView.tsx` | 辅助 | 瞬态增量实时检视子组件：呈现活跃增量列表、交互式用户修正录入表单、LWW 重写覆盖与前缀哈希校验 | ✅    |
| `PromptCacheConsolidationView.tsx` | 辅助 | 缓存一致性与归档子组件：双轨预览、一键归档落库；HUD 仅展示后端遥测，无数据时显示占位符 | ✅    |
| `TwoLayerDialecticStudioCard.tsx` | 核心 | Lab-only（`NEXT_PUBLIC_MEMORY_LABS=1`）两层上下文布局预览：Layer 1 用户消息尾快照、Layer 2 辩证调和控制台；未接入 live 中间件，命中率见聊天上下文环 | ✅    |
| `TwoLayerDialecticHudBar.tsx` | 辅助 | 两层辩证 4 维 HUD：前缀布局稳定提示、Layer 1/2 周期与辩证深度；不展示伪造缓存命中率 | ✅    |
| `BaseContextCacheView.tsx` | 辅助 | Layer 1 基础上下文与 Prompt Cache 检视子组件：呈现冻结 System 块、User 尾部注入块、持久 Cache Key 与单次编译仿真 | ✅    |
| `DialecticReconciliationConsoleView.tsx` | 辅助 | Layer 2 自适应辩证推理工作台子组件：支持配置矛盾事实并启动 1~3 遍正题/反题/合题辩证调和，展示置信度与合成事实 | ✅    |
| `DialecticCadenceControlsView.tsx` | 辅助 | Item 112 Lab：Layer 1/2 周期、辩证深度与 reasoning 等级调优（i18n；不承诺缓存命中率） | ✅    |
| `twoLayerDialecticFallbacks.ts` | 辅助 | 两层上下文解耦与辩证推理调和离线及单测仿真数据集 | ✅    |
| `BudgetGreedyPackingStudioCard.tsx` | 核心 | 预算贪心边际价值召回装箱中枢卡片：对标 FrankHu-HK/mnemosyne，给定 Token 预算贪心装满边际价值最高片段，区分计费与存储 Token 双轨计量 | ✅    |
| `BudgetPackingHudBar.tsx` | 辅助 | 装箱预算 4 维 HUD 监控条：呈现预算填满率、平均边际价值密度、存储 Token 离线节省量与语义冗余拦截量 | ✅    |
| `MarginalValuePackingView.tsx` | 辅助 | 边际价值装箱看板子组件：展示已入选片段列表、淘汰抑制片段分析与编译生成的 `<recalled_memories>` XML 上下文装箱代码块 | ✅    |
| `TokenAccountingInspectorView.tsx` | 辅助 | 双轨 Token 计量与调优控制台子组件：呈现计费 Token vs 存储 Token 成本节省对比、多样性惩罚权重 λ 与贪心背包填缝参数交互模拟 | ✅    |
| `budgetPackingFallbacks.ts` | 辅助 | 预算贪心边际价值召回装箱离线及单测仿真数据集 | ✅    |
| `MemoryCubeStudioCard.tsx` | 核心 | Memory Cube 空间治理与动态挂载中枢卡片：对标 MemOS Memory Cube，多智能体私有与共享记忆空间物理隔离，读写分离动态挂载调优与拦截防护 | ✅    |
| `MemoryCubeHudBar.tsx` | 辅助 | Memory Cube 4 维 HUD 监控条：呈现活跃 Cube 空间数、记忆记录量、挂载拓扑数与严格隔离拦截状态 | ✅    |
| `MemoryCubeMatrixView.tsx` | 辅助 | Memory Cube 空间矩阵卡片与记录检视器：支持 global_shared/project_workspace/agent_private/ephemeral_task 四大作用域过滤与新建 Cube | ✅    |
| `AgentMountTopologyTuner.tsx` | 辅助 | 智能体动态挂载拓扑调优器与屏障测试器：支持多 Cube 读写分离授权配置，实时发起写探针拦截验证与跨 Cube 联邦检索测试 | ✅    |
| `memCubeFallbacks.ts` | 辅助 | Memory Cube 空间治理离线与单测仿真数据集 | ✅    |
| `MarkdownChunkerStudioCard.tsx` | 核心 | 增量滑动窗口Markdown切片与重叠索引管道中枢卡片：对标 OpenClaw 切片与增量机制，400-token滑动窗口切片、80-token重叠、内容哈希增量感知、行级回溯水合与Token节省率遥测 | ✅    |
| `MarkdownChunkerHudBar.tsx` | 辅助 | Markdown切片引擎 4 维 HUD 监控条：呈现目标源文档、切片总量、相邻重叠预算、Token节省率与重新切片动作 | ✅    |
| `SlidingWindowVisualizerCard.tsx` | 辅助 | 滑动窗口切片可视化检视器：直观呈现切片序列、起止行号范围、内容哈希签名、代码块保护与行级回溯水合扩展上下文视图 | ✅    |
| `IncrementalDiffInspectorCard.tsx` | 辅助 | 内容哈希增量索引与 Token 节省检视器：呈现版本对比报告、复用/变更/废弃切片分布、进度条与免除重复调用Embedding API遥测 | ✅    |
| `markdownChunkerFallbacks.ts` | 辅助 | Markdown切片与增量索引离线仿真与预设长篇Markdown数据集 | ✅    |
| `MultiPlatformMemoryMigrationStudioCard.tsx` | 核心 | 全平台多格式记忆无缝迁移与导入引擎中枢卡片：对标 OpenClaw 迁移向导，一键扫描探测本地竞品资产、归一化认知分层映射预览、400/80滑动窗口切片导入与幂等审计台账 | ✅    |
| `MemoryMigrationHudBar.tsx` | 辅助 | 记忆迁移引擎 4 维 HUD 监控条：呈现本地探测资产数、支持生态数、已接纳记忆数与滑动分块数 | ✅    |
| `CompetitorAssetDetectorCard.tsx` | 辅助 | 本地竞品记忆资产探测器卡片：扫描并展示 OpenClaw/Hermes/MemOS/ChatGPT 候选文件路径、预估条目数与一键预填导入 | ✅    |
| `MigrationMappingPreviewCard.tsx` | 辅助 | 认知分层归一化映射与事实预览卡片：展示 Profile/Procedural/Semantic/Episodic 分类标识、标签与 SHA-256 去重哈希 | ✅    |
| `memoryMigrationFallbacks.ts` | 辅助 | 多平台记忆迁移离线与单测仿真数据集 | ✅    |

## 依赖



- `@/services/memory`、`@/store/*`、`@/components/primitives/*`
- 兄弟子目录 `../cards/`、`../dialogs/`、`../hooks/`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
