# memory/command-center/

## 架构概述

记忆命令中心：诊断、修复与高级编排的统一入口。门面负责面板编排，子面板按职责拆分，避免单文件承载全部诊断逻辑。

设置页 **Memory Command Center** 整体默认隐藏；本地/开发需 `NEXT_PUBLIC_MEMORY_LABS=1`（兼容 `NEXT_PUBLIC_MEMORY_LAB=1`）并重启 WebUI，且服务端 `MYRM_MEMORY_LABS=1`（见 `MemorySection.tsx`、`memoryLabs.ts`）。Two-layer studio 卡片同样受 labs 开关约束（见 `MemoryCommandCenterPanels.tsx`）。

## 文件清单

| 文件                                    | 地位 | 职责                                                             | I/O/P |
| --------------------------------------- | ---- | ---------------------------------------------------------------- | ----- |
| `MemoryCommandCenter.tsx`               | 门面 | 命令中心主布局：数据装配、面板编排与跨面板状态协调               | ✅    |
| `MemoryCommandCenterPanels.tsx`         | 核心 | 主内容区面板集合（概览/召回/健康等基础面板）                     | ✅    |
| `MemoryCommandCenterAdvancedPanels.tsx` | 核心 | 高级面板集合（容量剧场、偏好雷达、检索诊断等进阶视图）           | ✅    |
| `MemoryCommandCenterDoctorPanel.tsx`    | 核心 | 记忆医生面板：诊断项、自动修复动作与修复结果趋势                 | ✅    |
| `MemoryCommandCenterChrome.tsx`         | 辅助 | 命令中心外壳（标题、工具栏、tab 切换与操作区）                   | ✅    |
| `MemoryRecallBoundaryPanel.tsx`         | 辅助 | 召回边界面板：注入预算与截断披露                                 | ✅    |
| `CognitiveClockPanel.tsx`               | 核心 | 多频认知时钟状态面板：T0-T3 状态指示、前台打字让步指示与手动提炼 | ✅    |
| `MemoryEconomicsPanel.tsx`              | 核心 | 长程有状态任务记忆经济学剖析面板：三阶段开销、ROI 轨迹与沉睡治理 | ✅    |
| `MemoryEconomicsKpiCards.tsx`           | 辅助 | 经济学面板指标卡片子组件：三阶段时延细分、前缀缓存保持率与 ROI   | ✅    |
| `MemoryParasiticGovernanceList.tsx`     | 辅助 | 经济学面板沉睡治理子组件：低效沉睡记忆列表、单条与批量归档操作   | ✅    |
| `FourLayerPromotionAuditCard.tsx`       | 核心 | 四层记忆架构与三通道晋升审计面板：两步压缩方法卡、证据链接、规则遵守契约与原子回滚 | ✅    |
| `CodeGraphAssetCard.tsx`                | 核心 | 代码图谱记忆资产与影响面评估面板：工作区符号拓扑、修改前爆炸半径/调用链评估与资产探针 | ✅    |
| `EbbinghausLifecycleCard.tsx`           | 核心 | 艾宾浩斯遗忘衰减与分层生命周期流转卡片：三级水槽 HUD、周期评估迁移、冷记忆唤醒与冷库探针 | ✅    |
| `ColdArchiveRecordsView.tsx`            | 辅助 | 艾宾浩斯生命周期卡片子组件：呈现 COLD 冷存储归档数据切片与访问频次时间戳 | ✅    |
| `GraphRRFRetrievalCard.tsx`             | 核心 | 知识图谱与语义向量双路检索 RRF 融合卡片：双通道查询控制台、融合排名列表与节点快速注册 | ✅    |
| `GraphTraversalResultView.tsx`          | 辅助 | 知识图谱拓扑遍历子组件：呈现触达节点徽章、多跳关系路径展开与关联记忆 | ✅    |
| `HindsightReflectionCard.tsx`           | 核心 | 事后经验反思与失败任务回放缓冲卡片：避坑规则沉淀、前置预警探测与反思指标 HUD | ✅    |
| `HindsightWarningsView.tsx`             | 辅助 | 事后反思卡片子组件：呈现高风险避坑警示卡片与推荐纠偏建议动作 | ✅    |
| `CodeMemoryCompactionCard.tsx`          | 核心 | 代码语义记忆骨架化压缩引擎卡片：Token 预算感知、AST 结构多级降级与压缩节约率分析 | ✅    |
| `CodeSkeletonPreviewView.tsx`           | 辅助 | 代码记忆压缩卡片子组件：呈现抽象层级徽章、代码骨架块预览与 Token 节省对比 | ✅    |
| `GeneEvolutionInspectorCard.tsx`        | 核心 | 因果经验基因合成与达尔文演化卡片：前置征兆探针、被证伪假设避坑建议与置信度动态惩罚 | ✅    |
| `GeneAdviceListView.tsx`                | 辅助 | 经验基因卡片子组件：呈现规划期命中经验建议、触发征兆徽章与死胡同避坑清单 | ✅    |
| `AutoRecallGovernanceCard.tsx`          | 核心 | 高敏感场景经验自动召回门禁卡片：5 大敏感触发识别、5 轮滑窗去重与 Fail-Open 神经重排遥测 | ✅    |
| `AutoRecallFilterTraceView.tsx`         | 辅助 | 自动召回卡片子组件：呈现审计裁决徽章、去重漏斗指标与最终注入记忆清单 | ✅    |
| `GroundTruthDriftDefenseCard.tsx`       | 核心 | Ground Truth 真实性漂移防御与过时记忆熔断卡片：物理文件存在性与 AST 符号扫描、过时前缀装配与置信度衰减 | ✅    |
| `DriftReferenceAuditView.tsx`           | 辅助 | 真实性漂移防御卡片子组件：呈现物理不一致证据列表、漂移类型徽标与装配效果预览 | ✅    |
| `SovereignMigrationInspectorCard.tsx`   | 核心 | 全量数字资产主权打包、跨机无损还原与多源迁入卡片：.myrmpkg 加密便携导出、路径解绑重映射与竞品智能体迁入 | ✅    |
| `CompetitorAssetDetectionView.tsx`      | 辅助 | 主权迁移卡片子组件：呈现本机第三方智能体资产（Hermes/Claude Code/Codex）嗅探结果与一键迁入 | ✅    |
| `CrossAgentConflictArbitrationCard.tsx` | 核心 | 跨智能体可组合上下文隔离与分歧仲裁套件卡片：4层物理上下文隔离投影 (80%+ KV Cache 保护) • 3级梯队分歧确定性仲裁探针 • 跨智能体移交包防篡改验签 | ✅    |
| `ComposableContextProjectionView.tsx`   | 辅助 | 跨智能体可组合上下文子组件：4层虚拟引用投影 HUD、KV-Cache 指标与各层明细展示 | ✅    |
| `KnowledgeGraphPoisoningShieldCard.tsx` | 核心 | 知识图谱抽取前合规前筛与防投毒哨兵卡片：隐藏 HTML 注释指令扫描、零宽隐写字符剥离与系统指令越权熔断阻断 | ✅    |
| `IntegrationRetainedContextPurgeCard.tsx` | 核心 | 集成断连上下文治理与溯源撤销卡片：对标并超越 OpenAI Dots 隐私规范、已摄入上下文透明盘点、双模断连选择性 Purge 与来源撤销账本 | ✅    |
| `ProjectLivingFactLedgerCard.tsx` | 核心 | 长期项目动态事实状态账本与四层上下文投影卡片：决议/否决/约束全景账本、4-Tier 动态投影仿真器与基于验证结果的能力沉淀飞轮 | ✅    |
| `FirstEncounterReportCard.tsx` | 核心 | 历史会话轻量采样与“初见报告”冷启动卡片：多源 Agent 探测雷达、首2尾12关键帧采样、香农熵双轨零泄漏脱敏与个人技术画像一键入库 | ✅    |
| `ScreenObservationSafetyCard.tsx` | 核心 | 屏幕观测记忆防注入与描述性事实门禁卡片：不可信证据语义隔离、强制第三人称语法校验与防单次过度提升门禁 | ✅    |
| `TaskTriadTrajectoryCard.tsx` | 核心 | 超长任务三元状态轨迹黑匣子卡片：已达成里程碑、死胡同防循环规则拦截雷达、在途约束中途保护与单步避坑快照 HUD | ✅    |
| `ActivityCompactorCard.tsx` | 核心 | 分级滑动时间窗口活动日志折叠与提炼管道卡片：10min 动作算法去抖折叠 (0 Token)、6h 宏观业务里程碑提纯与 24h 长期偏好归档 | ✅    |
| `ActivityCompactorTimelineView.tsx` | 辅助 | 分级活动折叠卡片子组件：呈现微观 10min 纯算法折叠切片与 6h 宏观里程碑时间线列表 | ✅    |
| `NoiseFreeMemoryCard.tsx` | 核心 | 工具回执噪声剥离与单调递增清除代次套件卡片：物理剥离工具调用/回执、代码级 PII 正则拦截网关与 Epoch Fencing 防幽灵复活 | ✅    |
| `NoiseFreeMemoryEpochView.tsx` | 辅助 | 无噪声记忆套件子组件：呈现当前代次 (Epoch) HUD、已持久化事实列表与幽灵写入拦截统计 | ✅    |
| `PrivateNotebookCard.tsx` | 核心 | 透明可检视模型私有笔记本卡片：对标 Codex PR #42385 超越版、Notes 5 工具操作台、历史交互检索与平滑跨窗口接力 | ✅    |
| `PrivateNotebookNotesListView.tsx` | 辅助 | 私有笔记本卡片子组件：呈现透明 Markdown 笔记索引、行数统计、实时检视与人工纠偏覆写 | ✅    |
| `PrivateNotebookHistoryView.tsx` | 辅助 | 私有笔记本卡片子组件：跨上下文窗口长程交互历史检索、归档窗口列表与流式条目展现 | ✅    |
| `PrivateNotebookHandoverView.tsx` | 辅助 | 私有笔记本卡片子组件：跨窗口平滑移交 (new_context) 表单、交接原因录入与状态报告 | ✅    |
| `JobCompoundingCard.tsx` | 核心 | 业务岗位说明书与经验复利沉淀卡片：对标 Grok Bot 蓝皮书最佳实践、立项四要素向导、领域规则与成熟度成长看板 | ✅    |
| `JobDescriptionBuilderView.tsx` | 辅助 | 岗位复利卡片子组件：立项四要素向导表单（业务目标范围、绑定工具源、工作风格调性、自主/审批动作边界） | ✅    |
| `CompoundingMaturityView.tsx` | 辅助 | 岗位复利卡片子组件：四级成熟度进度阶梯、已沉淀领域规则清单、审批边界试运行模拟器 | ✅    |
| `RevocableProvenanceCard.tsx` | 核心 | 可撤销带溯源记忆与梦境日记卡片：对标 OpenClaw 2.0，双向溯源图谱挂载、定点无损原子遗忘（保证底座不可变）与后台梦境日记看板 | ✅    |
| `ProvenanceQualifiedMemoryListView.tsx` | 辅助 | 溯源记忆子组件：呈现带 Session/Message/Quote 双向溯源图谱事实列表、原子遗忘定点撤销与快速沉淀表单 | ✅    |
| `DreamDiaryDeckView.tsx` | 辅助 | 梦境日记子组件：呈现后台模型梦境蒸馏周期卡片、扫描轮次/晋升事实/剪枝去重指标与手动记录表单 | ✅    |
| `FourTierPersistentMemoryCard.tsx` | 核心 | 四重持久记忆体系与 FTS5 梦境自维护卡片：对标小米 MiMo Code/Desktop，项目-会话-进度-全局四重解耦、SQLite FTS5 毫秒全文召回与 7 天 /dream 自维护循环 | ✅    |
| `FourTierMemoryTierListView.tsx` | 辅助 | 四重分层记忆子组件：4 栏 Scope 标签切换（项目/会话/进度/全局）、记忆切片浏览/详情展开/单条删除与新建表单 | ✅    |
| `FourTierFtsSearchAndDreamView.tsx` | 辅助 | FTS5 检索与梦境压缩子组件：SQLite FTS5 毫秒级全文召回控制台、BM25 评分结果高亮切片与 /dream 梦境压缩维护报告 | ✅    |
| `TemporalKnowledgeGraphCard.tsx` | 核心 | 时序知识图谱衰减与互斥事实原子消解卡片：深度借鉴 mem/graphiti 与 mem/OpenViking，时序边失效、互斥事实原子消解 superseded_by 与 30 天指数半衰期动态衰减评分 | ✅    |
| `TemporalGraphEvolutionTimelineView.tsx` | 辅助 | 时序关系演进子组件：呈现有效关系/已失效历史边演进时间线、前序-后继版本谱系追溯与冲突消解表单 | ✅    |
| `TemporalDecayScorerConsoleView.tsx` | 辅助 | 半衰期衰减与实体节点管理子组件：半衰期动态衰减评分探针计算器、实体节点管理列表与新建节点表单 | ✅    |
| `DiskMemoryReconciliationCard.tsx` | 核心 | 磁盘文件与 FTS5 双向对账及显式写入门禁卡片：深度汲取小米 MiMo Code 生产级源码，Direction A 增量建索、Direction B 僵尸索引修剪与读写严格解耦门禁 | ✅    |
| `DiskReconciliationAuditConsoleView.tsx` | 辅助 | 双向对账巡检子组件：呈现待对账目录指定表单、最新审计报告指标卡片与 FTS5 搜索一致性验证 | ✅    |
| `WriteGatePermissionInspectorView.tsx` | 辅助 | 显式写入门禁权限子组件：呈现 4 种安全策略切换、读写解耦状态说明与实时门禁裁决探针 | ✅    |
| `GitNativeKnowledgeBundleCard.tsx` | 核心 | Git 原生项目知识库与记忆防腐烂门禁卡片：基于 Google OKF v0.2 标准，随代码版本化流转、两阶段渐进式披露、stale_after 显式保质期与人机防篡改信任天平 | ✅    |
| `OkfKnowledgeBundleBrowserView.tsx` | 辅助 | 知识包卡片浏览器子组件：呈现目录挂载、第一阶段轻量披露清单（<300 Tokens）、治理层级过滤与第二阶段深入检视 | ✅    |
| `OkfMemoryRotAuditConsoleView.tsx` | 辅助 | 防腐烂门禁与 BM25 检索子组件：呈现保质期过期巡检、人机防篡改验签报告与亚毫秒内存 BM25 词法检索 | ✅    |
| `ConversationLineageDefenseCard.tsx` | 核心 | 会话血统代际去重与自动化降权卡片：深度汲取 Hermes Agent PR #19434，来源感知降权破除高频 Cron 召回盲区、血统根去重消除多代冗余、非对称渐进水合削减 70%+ Token | ✅    |
| `ConversationLineageDedupView.tsx` | 辅助 | 血统去重视图子组件：呈现 lineage_root_id 家族代表世代、折叠历史祖先切片展开与演化谱系 | ✅    |
| `AutomationDemotionAuditConsoleView.tsx` | 辅助 | 自动化降权控制台子组件：呈现来源降权系数调优、Top-1 展开视窗 vs Top-2..N 紧凑卡片与 Token 节约报告 | ✅    |
| `PromptCachePreservingDeltaCard.tsx` | 核心 | 会话内记忆更新检视：稳定 system 前缀 + human 尾部的布局预览；默认绑定当前聊天 session；命中率见聊天上下文环，此处不展示伪造百分比 | ✅    |
| `EphemeralDeltaLiveInspectorView.tsx` | 辅助 | 瞬态增量实时检视子组件：呈现活跃增量列表、交互式用户修正录入表单、LWW 重写覆盖与前缀哈希校验 | ✅    |
| `PromptCacheConsolidationView.tsx` | 辅助 | 缓存一致性与归档子组件：双轨预览、一键归档落库；HUD 仅展示后端遥测，无数据时显示占位符 | ✅    |
| `DeterministicRuleCascadeCard.tsx` | 核心 | 确定性规则级联与五维预过滤卡片：深度融合 Claude Code 工程规范自顶向下确定性级联加载与物理级五维元数据隔离拦截，终结向量碰运气与越权泄露 | ✅    |
| `DeterministicRuleCascadeHierarchyView.tsx` | 辅助 | 目录穿透级联子组件：呈现从根到叶目录规则继承树、高深度覆盖低深度同名冲突、三级来源权威度徽标与生效规则列表 | ✅    |
| `FiveDimEvidencePreFilterAuditView.tsx` | 辅助 | 五维物理预过滤审计子组件：呈现 Scope/Authority/Half-life/Confidence/Permission 5 维边界调优、拒绝原因统计与安全记忆穿透对比 | ✅    |
| `TemporalRelationalBacktrackingCard.tsx` | 核心 | 时序因果锚点与跨会话实体反向回溯卡片：深度攻克开篇“吃火锅 ↔ 打边炉哪个客户”经典痛点，三元组锚定、同义方言倒查与原文证据强绑定 | ✅    |
| `CrossSessionBacktrackConsoleView.tsx` | 辅助 | 跨会话反向回溯控制台子组件：呈现口语化方言动作线索反查、毫秒级目标客体锁定、出处对话切片高亮与综合因果推断 | ✅    |
| `RelationalAnchorGraphView.tsx` | 辅助 | 时序因果拓扑子组件：呈现结构化实体-动作-时间三元组列表、同义词方言映射簇、新建三元组录入与原文证据强绑定 | ✅    |
| `MemoryCuratorStudioCard.tsx` | 核心 | 记忆策展工作台与 Markdown 双向同步卡片：深度汲取 OpenClaw/Hermes 纯文本人类可读可编辑哲学，工作区 MEMORY.md 镜像毫秒级热重载、所见即所得卡片流策展与一键隐私物理擦除 | ✅    |
| `MemoryCuratorStreamView.tsx` | 辅助 | 所见即所得卡片流子组件：呈现认知分类与状态筛选药丸、反乱记待审人类门禁确认/驳回、原地即时编辑与一键物理抹除 | ✅    |
| `MemoryCuratorWorkspaceView.tsx` | 辅助 | 工作区 Markdown 镜像子组件：呈现原生纯文本 Markdown 编辑器、双向对账 Diff 统计、从磁盘热重载同步至 SQLite 与导出镜像 | ✅    |
| `MemoryCuratorHudBar.tsx` | 辅助 | 策展 4 维 HUD 监控条：呈现生效记忆、待审门禁、双向镜像同步延迟与认知分类分布 | ✅    |
| `MemoryCuratorAddForm.tsx` | 辅助 | 折叠式新记忆录入表单：录入标题、分类、详细内容与标签并即时刷盘 | ✅    |
| `MemoryCuratorEntryCard.tsx` | 辅助 | 单条记忆卡片项：支持原地编辑、状态徽章、置信度与一键物理抹除 | ✅    |
| `curatorFallbacks.ts` | 辅助 | 策展工作台离线与单测仿真数据集 | ✅    |
| `PeerCognitionStudioCard.tsx` | 核心 | 社会认知实体图谱与常驻画像卡中枢卡片：对标 Hermes+Honcho 官方实践，以参与者 Peer 为中心组织记忆，打破孤立事实表局限，常驻 Peer Card 自演化与多智能体角色对齐 | ✅    |
| `PeerCognitionHudBar.tsx` | 辅助 | 社会认知 4 维 HUD 监控条：呈现常驻 Peer 实体数、语义关系边数、累计协作演化频次与低 Token 上下文投影开销 | ✅    |
| `PeerEntityGraphExplorerView.tsx` | 辅助 | 实体拓扑与关系边检索探索子组件：支持按用户/智能体/项目/审查者筛选实体，呈现 asserts/approves/collaborates/governs 语义边与动态建立关系 | ✅    |
| `AddRelationEdgeForm.tsx` | 辅助 | 实体图谱关系边新增抽屉表单：支持选择主客体、语义动词、情境依据与客体 Peer 标识，严格符合 a11y 与 <400 行硬上限 | ✅    |
| `PeerPersonaCardStudioView.tsx` | 辅助 | 常驻画像卡与角色对齐子组件：展示明确职责边界、决策风格、常驻偏好字典、交互反馈自演化模拟与低 Token 提示词投影编译 | ✅    |
| `RegisterPeerFormView.tsx` | 辅助 | 参与者 Peer 注册表单子组件：支持录入 Peer ID、类型、名称与角色头衔并提交初始化，严格符合 a11y 与 <400 行硬上限 | ✅    |
| `peerCognitionFallbacks.ts` | 辅助 | 社会认知实体图谱与画像卡离线及单测仿真数据集 | ✅    |
| `TwoLayerDialecticStudioCard.tsx` | 核心 | Lab-only（`NEXT_PUBLIC_MEMORY_LAB=1`）两层上下文布局预览：Layer 1 用户消息尾快照、Layer 2 辩证调和控制台；未接入 live 中间件，命中率见聊天上下文环 | ✅    |
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
| `AutoMemoryConsolidationStudioCard.tsx` | 核心 | 闲置自适应与双门禁记忆沉淀中枢卡片：对标 CodeX 自动化记忆双门禁，对话太短不记、额度没了不记，闲置自适应唤醒提取六维资产切片 | ✅    |
| `AutoMemoryGatingHudBar.tsx` | 辅助 | 自动记忆沉淀 4 维 HUD 监控条：呈现综合准入判定、闲置感知计时、对话轮数与信息密度、Token 预算保护与开销比 | ✅    |
| `SixDimensionalArtifactViewer.tsx` | 辅助 | 六维结构化记忆切片全景看板：直观展示工作目录、关键主题、用户偏好、领域经验、失败教训、工具调用习惯六大工程维度 | ✅    |
| `GatingRulesConfigView.tsx` | 辅助 | 双门禁准入与闲置自适应阈值调优面板：支持调节闲置超时时长、最小轮数门禁、信息密度阈值、Token 保护底线与开销占比上限 | ✅    |
| `autoMemoryConsolidationFallbacks.ts` | 辅助 | 闲置自适应与双门禁记忆沉淀离线及单测仿真数据集 | ✅    |
| `MemoryCubeStudioCard.tsx` | 核心 | Memory Cube 空间治理与动态挂载中枢卡片：对标 MemOS Memory Cube，多智能体私有与共享记忆空间物理隔离，读写分离动态挂载调优与拦截防护 | ✅    |
| `MemoryCubeHudBar.tsx` | 辅助 | Memory Cube 4 维 HUD 监控条：呈现活跃 Cube 空间数、记忆记录量、挂载拓扑数与严格隔离拦截状态 | ✅    |
| `MemoryCubeMatrixView.tsx` | 辅助 | Memory Cube 空间矩阵卡片与记录检视器：支持 global_shared/project_workspace/agent_private/ephemeral_task 四大作用域过滤与新建 Cube | ✅    |
| `AgentMountTopologyTuner.tsx` | 辅助 | 智能体动态挂载拓扑调优器与屏障测试器：支持多 Cube 读写分离授权配置，实时发起写探针拦截验证与跨 Cube 联邦检索测试 | ✅    |
| `memCubeFallbacks.ts` | 辅助 | Memory Cube 空间治理离线与单测仿真数据集 | ✅    |
| `DreamCognitiveStudioCard.tsx` | 核心 | 梦境认知重组与智能体成长日记中枢卡片：对标 MemOS Dream Plugin，后台非阻塞梦境反思、高维洞察提取与白盒演进日记展示 | ✅    |
| `DreamCognitiveHudBar.tsx` | 辅助 | 梦境认知 4 维 HUD 监控条：呈现总成长日记数、认知突变动作量、活跃 Cube 空间数与后台非阻塞反思运行状态 | ✅    |
| `GrowthDiaryTimelineView.tsx` | 辅助 | 智能体心智进化成长日记时间轴检视组件：呈现演化标题、动机徽章、反思叙事、主题标签、Actions 列表与 Markdown 视图渲染 | ✅    |
| `DreamCognitiveSynthesisConsoleView.tsx` | 辅助 | 梦境认知重组触发控制台：支持配置会话碎片与关联 Memory Cube，实时触发非阻塞梦境整合并展示执行报告与动作详情 | ✅    |
| `dreamCognitiveFallbacks.ts` | 辅助 | 梦境认知重组与成长日记离线及单测仿真数据集 | ✅    |
| `QuadrupleRetrievalStudioCard.tsx` | 核心 | 目标驱动四路并行检索与推理重排工作台卡片：对标 MemOS 混合检索架构，前置 TaskGoalParser 消除自然语言模糊噪音，四路并行召回矩阵与 Reasoner 语义推理重排 | ✅    |
| `QuadrupleRetrievalHudBar.tsx` | 辅助 | 四路检索 4 维 HUD 监控条：呈现总索引数、4 通道激活状态、平均端到端延迟与通道权重乘数 | ✅    |
| `TaskGoalParserConsoleView.tsx` | 辅助 | 目标意图前置解构控制台：直观展示自然语言查询解构结果、实体锚点、词法分词、元数据过滤与置信度 | ✅    |
| `QuadrupleRecallMatrixView.tsx` | 辅助 | 四路并行召回矩阵看板：直观展示 Graph 拓扑、Vector 稠密、Lexical 词法与 Metadata 过滤四通道命中量与融合增益 | ✅    |
| `ReasonerHarmonizerCard.tsx` | 辅助 | 推理重排单项条目卡片：展示排名、多通道徽章、Reasoner 裁决徽章（Boost/Keep/Stale Penalty/Suppress）与可展开审计推导 | ✅    |
| `quadrupleRetrievalFallbacks.ts` | 辅助 | 目标驱动四路并行检索离线与单测仿真数据集 | ✅    |
| `SqliteVecStudioCard.tsx` | 核心 | 基于SQLite与sqlite-vec的嵌入式轻量向量存储工作台卡片：对标 OpenClaw 嵌入式存储方案，展示单文件零容器自包含引擎指标、Native SIMD vec0/Process BLOB 双轨模式与时间衰减稠密检索 | ✅    |
| `SqliteVecHudBar.tsx` | 辅助 | SQLite-Vec 向量引擎 4 维 HUD 监控条：呈现引擎双轨运行模式、文件体积、向量集合数、存储文档总数与指标刷新 | ✅    |
| `SqliteVecQueryConsoleView.tsx` | 辅助 | 稠密向量近邻检索控制台：支持配置测试查询向量、艾宾浩斯时间半衰期衰减开关与相似度过滤阈值 | ✅    |
| `SqliteVecSearchResultsView.tsx` | 辅助 | 稠密向量检索命中结果与衰减比对视图：展示原始余弦相似度、时间衰减后有效得分、衰减留存率与文档元数据标签 | ✅    |
| `sqliteVecFallbacks.ts` | 辅助 | 基于SQLite与sqlite-vec的嵌入式向量存储离线与单测仿真数据集 | ✅    |
| `VectorSpaceGuardStudioCard.tsx` | 核心 | Embedding模型维度与向量空间完整性校验守卫中枢卡片：对标 OpenClaw 向量一致性校验，防范多模型混用基底污染、预检兼容性、空间指纹绑定与安全重建迁移 | ✅    |
| `VectorSpaceGuardHudBar.tsx` | 辅助 | 向量空间守卫 4 维 HUD 监控条：呈现集合受保护状态、基底模型、维度与度量方式、已索引向量量级与状态刷新 | ✅    |
| `VectorSpaceConsistencyCheckerCard.tsx` | 辅助 | 运行时模型指纹与预检校验控制台：支持预设及自定义模型指纹选择、自动绑定空集合开关、兼容性白盒比对与异常处理推荐动作 | ✅    |
| `VectorSpaceReindexerCard.tsx` | 辅助 | 空间迁移与向量重索引流水线控制台：支持配置目标模型基底、一键触发受守卫保护的原子化重新嵌入与指纹同步更新 | ✅    |
| `vectorSpaceGuardFallbacks.ts` | 辅助 | 向量空间守卫与模型指纹离线与单测仿真数据集 | ✅    |
| `MarkdownChunkerStudioCard.tsx` | 核心 | 增量滑动窗口Markdown切片与重叠索引管道中枢卡片：对标 OpenClaw 切片与增量机制，400-token滑动窗口切片、80-token重叠、内容哈希增量感知、行级回溯水合与Token节省率遥测 | ✅    |
| `MarkdownChunkerHudBar.tsx` | 辅助 | Markdown切片引擎 4 维 HUD 监控条：呈现目标源文档、切片总量、相邻重叠预算、Token节省率与重新切片动作 | ✅    |
| `SlidingWindowVisualizerCard.tsx` | 辅助 | 滑动窗口切片可视化检视器：直观呈现切片序列、起止行号范围、内容哈希签名、代码块保护与行级回溯水合扩展上下文视图 | ✅    |
| `IncrementalDiffInspectorCard.tsx` | 辅助 | 内容哈希增量索引与 Token 节省检视器：呈现版本对比报告、复用/变更/废弃切片分布、进度条与免除重复调用Embedding API遥测 | ✅    |
| `markdownChunkerFallbacks.ts` | 辅助 | Markdown切片与增量索引离线仿真与预设长篇Markdown数据集 | ✅    |
| `DualEngineHybridSearchStudioCard.tsx` | 核心 | 双引擎FTS与向量混合重排与无缝平滑降级中枢卡片：对标 OpenClaw 检索融合，双引擎并行检索、自适应多因子RRF调优、艾宾浩斯时间衰减与向量断路器容灾控制台 | ✅    |
| `HybridSearchHudBar.tsx` | 辅助 | 双引擎检索与断路器 5 维 HUD 监控条：呈现检索模式、断路器健康状态、索引总量、同义词规模与跳闸熔断次数 | ✅    |
| `AdaptiveRrfRankVisualizerView.tsx` | 辅助 | 自适应多因子 RRF 融合重排调优视图：动态滑块调整 RRF k 值、FTS 权重、Vector 权重、重要性权重，并展示实时重排序列与时间衰减因子 | ✅    |
| `CircuitBreakerFallbackConsoleView.tsx` | 辅助 | 向量断路器与平滑降级控制台：展示 CLOSED / OPEN / HALF_OPEN 三态流转拓扑、毫秒级短路拦截指标与注入故障熔断演练 | ✅    |
| `hybridSearchFallbacks.ts` | 辅助 | 双引擎混合检索与断路器容灾离线与单测仿真数据集 | ✅    |
| `MultiPlatformMemoryMigrationStudioCard.tsx` | 核心 | 全平台多格式记忆无缝迁移与导入引擎中枢卡片：对标 OpenClaw 迁移向导，一键扫描探测本地竞品资产、归一化认知分层映射预览、400/80滑动窗口切片导入与幂等审计台账 | ✅    |
| `MemoryMigrationHudBar.tsx` | 辅助 | 记忆迁移引擎 4 维 HUD 监控条：呈现本地探测资产数、支持生态数、已接纳记忆数与滑动分块数 | ✅    |
| `CompetitorAssetDetectorCard.tsx` | 辅助 | 本地竞品记忆资产探测器卡片：扫描并展示 OpenClaw/Hermes/MemOS/ChatGPT 候选文件路径、预估条目数与一键预填导入 | ✅    |
| `MigrationMappingPreviewCard.tsx` | 辅助 | 认知分层归一化映射与事实预览卡片：展示 Profile/Procedural/Semantic/Episodic 分类标识、标签与 SHA-256 去重哈希 | ✅    |
| `memoryMigrationFallbacks.ts` | 辅助 | 多平台记忆迁移离线与单测仿真数据集 | ✅    |
| `ProactiveDecisionAssistStudioCard.tsx` | 核心 | 主动历史踩坑预警与决策干预中枢卡片：对标个人 AI 操作系统主动决策协助，影子意图实时嗅探、因果三元组历史教训反查、会话级静音与非侵入式 Callout 预警 | ✅    |
| `DecisionAssistHudBar.tsx` | 辅助 | 决策辅助 4 维 HUD 监控条：呈现哨兵运行状态、已录入踩坑教训数、会话静音范围与亚毫秒级嗅探延迟 | ✅    |
| `ShadowDecisionDetectorView.tsx` | 辅助 | 影子决策意图嗅探与演练视图：极速正则状态机预检，严格区分探讨咨询（静默放行）与实质技术选型（触发因果反查） | ✅    |
| `ProactivePitfallCalloutView.tsx` | 辅助 | 非侵入式轻量 Callout 预警卡片：高亮呈现历史故障复盘、已验证替代方案、版本环境漂移提示与一键采纳/静音动作 | ✅    |
| `decisionAssistFallbacks.ts` | 辅助 | 主动历史踩坑预警与决策干预离线与单测仿真数据集 | ✅    |
| `ExperienceCompoundingStudioCard.tsx` | 核心 | 个人经验资产复利演进与自动凝练中枢卡片：对标个人 AI 操作系统知识复利飞轮，有界对数加固、黄金准则语义凝练、双层谱系回退与时效冷退火 | ✅    |
| `ExperienceCompoundingHudBar.tsx` | 辅助 | 经验复利 4 维 HUD 监控条：呈现活跃热碎片数、凝练黄金准则数、冷退火沉降数与平均复利权重倍率 | ✅    |
| `GoldenRulesCatalogView.tsx` | 辅助 | 高阶黄金准则库全景卡片列表：展示 canonical 准则、提炼推导依据、置信度评分徽章与双层谱系撤销回退动作 | ✅    |
| `ActiveExperiencesPoolView.tsx` | 辅助 | 活跃热经验池与加固控制台：展示活跃碎片、半衰期动态延长、常驻租约/临时标签与一键采纳加固操作 | ✅    |
| `experienceCompoundingFallbacks.ts` | 辅助 | 经验资产复利演进与自动凝练离线与单测仿真数据集 | ✅    |

## 依赖



- `@/services/memory`、`@/store/*`、`@/components/primitives/*`
- 兄弟子目录 `../cards/`、`../dialogs/`、`../hooks/`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
