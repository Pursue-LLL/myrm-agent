# deliverable-inspector/

## 架构概述

本模块实现办公多形态交付物（Slides/Doc/Sheet/Markdown）实时核验器与局部精准修改/分片重试交互台。
彻底解决办公 Agent 生成长文档/PPT/数据表/研报时一旦某单页或局部表格有缺陷，用户只能整份重新生成、导致格式错乱且极大浪费 Token 的恶性痛点。
支持结构化大纲树与幻灯片单页点选激活、局部针对性 Targeted Prompt 精准增量重做、版本间差异可视化比对与一键无损回滚。对标千问办公、豆包工作、WorkBuddy 办公交付可核验与失败接管精髓并超越。

## 文件组织

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `deliverableInspectorTypes.ts` | Types | 核心数据模型契约（DeliverableNode, DeliverableSnapshot, SelectivePatchRequest, SnapshotDiffItem） | [INPUT] 无外部运行时依赖<br>[OUTPUT] 交付物大纲节点、局部补丁与版本快照类型<br>[POS] 交付物核验数据模型事实源 |
| `deliverableAstParser.ts` | Logic | 多形态工件 AST 大纲拆解、局部节点 Patch 合并与快照 Diff 算法引擎 | [INPUT] 原始工件文本内容与类型<br>[OUTPUT] 结构化大纲节点树、快照与比对结果<br>[POS] 局部差分与重试核心算法 |
| `DeliverableOutlineNavigator.tsx` | UI | 左侧大纲树与幻灯片缩略列表导航组件（节点过滤、状态徽标与点选激活） | [INPUT] DeliverableNode 节点数组<br>[OUTPUT] 可交互大纲导航与页签选择<br>[POS] 交付物结构概览与导航侧栏 |
| `DeliverableNodePatchBar.tsx` | UI | 局部精准针对性 Targeted Prompt 重做工具条（快捷预设、模式切换与 loading 态） | [INPUT] 当前选中节点与补丁提交回调<br>[OUTPUT] 局部修改提示词输入与触发器<br>[POS] 局部单点重试交互栏 |
| `DeliverableSnapshotDiffModal.tsx` | UI | 版本快照演变时间线、节点差异比对与一键无损回退模态框 | [INPUT] SnapshotDiffItem 差异项数组<br>[OUTPUT] 语义化可视化 Diff 比对对话框<br>[POS] 交付物版本审计与回滚界面 |
| `DeliverableInspector.tsx` | Core | 交付物核验总控交互台（集成导航、主视口、局部微调与版本管理） | [INPUT] 交付物文本、类型及更新回调<br>[OUTPUT] 完整可交互的多形态工件核验器主视图<br>[POS] 顶层聚合主工作表面 |
| `index.ts` | Facade | 门面统一导出 | [INPUT] 内部所有子模块<br>[OUTPUT] 统一向外部提供公共 API<br>[POS] 模块对外唯一门面 |
