# MultiRoleRelayStateProgressTimelineAndArtifactForkDiffSuite 架构设计

## 1. 核心定位
本套件破除长程多智能体协同流水线（如调研员➔分析师➔撰稿人）中的“黑盒焦虑”与“不可控交付”，为用户提供全透明的时序阶梯进度、中间工件原子快照透视，以及基于中间产物的分支修改与双向对比（Artifact Fork & Diff）能力。

## 2. 模块分层
- `multiRoleRelayTypes.ts`: 多智能体接力角色、流水线阶段状态机、阶段交接原子快照、分支修改（Fork Branch）与 Diff 契约；
- `relayPipelineEngine.ts`: 纯算法层，计算多角色接力完成率与当前活跃角色、逐行 Diff 分析（Added/Removed/Unchanged）、生成分支快照与推进下一棒状态流转；
- `useMultiRoleRelayStore.ts`: 集中式 Zustand 状态管理，维护三棒接力状态、当前查看快照、分支修改工作台显隐，并派发全局分支事件；
- `MultiRoleRelayStepTimeline.tsx`: 顶置阶梯时序胶囊指示器，支持一键点击透视任意前置角色的中间产物快照；
- `StageArtifactSnapshotViewer.tsx`: 阶段中间产物原子展示卡，清晰呈现角色元数据、Token 消耗、版本及“分支微调”入口；
- `ArtifactForkDiffStudio.tsx`: 双栏/逐行差量对比与源码编辑工作室，支持自定义分支名与修改备注，一键提交推向下游 Agent。
