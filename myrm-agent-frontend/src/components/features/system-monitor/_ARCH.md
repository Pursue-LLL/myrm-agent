# components/features/system-monitor/

## 架构概述

本地与沙箱系统级可观测性监控层，聚焦端口占用一键排查、父子进程树溯源（Launch Lineage）以及高耗与僵尸进程安全查杀。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.ts` | 类型 | 端口占用进程与父子派生链 TypeScript 契约定义 | ✅ |
| `ProcessLineageView.tsx` | 组件 | 进程启动父子调用树面包屑与高耗进程橙色预警视图 | ✅ |
| `PortConflictModal.tsx` | 组件 | 端口冲突检测弹窗、占用详情透视与一键安全查杀交互视窗 | ✅ |
| `CausalTraceWaterfallView.tsx` | 组件 | 单次请求因果 TraceSpan 树时序瀑布图、阶段耗时占比与元数据属性展开视图 | ✅ |
| `MultiTierHealthBadge.tsx` | 组件 | 组件支撑层 (Component) 与入口网关层 (Ingress) 能力分层健康大盘卡片 | ✅ |
| `AgentDoctorWizard.tsx` | 组件 | 智能体四大失效表象诊断向导、六大断点时序流水与就地重发控制台 | ✅ |
| `AgentDiagnosticCapsule.tsx` | 组件 | 智能体运行异常轻量诊断胶囊，提供异常表象即时提示与向导触发 | ✅ |
| `RetrievalDecisionTreeView.tsx` | 组件 | 上下文分层检索下钻决策树可视化、节点折叠/展开与剪枝诱因透视视图 | ✅ |
| `RetrievalTraceDrawer.tsx` | 组件 | 检索决策树控制台抽屉与 OpenViking 风格实验场参数重算微调器 | ✅ |
| `BudgetQuotaIndicator.tsx` | 组件 | 任务多维资源与时间/Token/积分预算配额水位与熔断预警指示器 | ✅ |
| `HybridResourceLedgerCard.tsx` | 组件 | 物理硬件占用与认知 Token 双轨混合全景对账单卡片 (AFP 协议) | ✅ |
| `TaskAccelerationBadge.tsx` | 组件 | 单任务白领劳务效能加速倍率实时徽章与一键复制战报组件 | ✅ |
| `ProductivityRoiDashboard.tsx` | 组件 | 月度生产力投资回报透视大盘与高频劳务节省工时分类排行看板 | ✅ |
| `SandboxSelfHealButton.tsx` | 组件 | 沙箱卡死一键就地热重启自愈按钮，支持 10 秒倒计时防抖与 Volume 数据完整性保证 | ✅ |
| `InAppDiagnosticModal.tsx` | 组件 | 端内沙箱现场全景诊断打包展示、PII 自动脱敏态势与闪电工单极速提交弹窗 | ✅ |
| `BudgetTierAlertBanner.tsx` | 组件 | 多阶梯式预算风控状态条幅（50% 水位提示、80% 自适应降级与 100% 挂起拦截）与快捷追加预算卡片 | ✅ |
| `TokenBurnRateHUD.tsx` | 组件 | 海量并发 Agent 编排 Token 燃速全景仪表盘、三阶梯进度刻度计与活跃子 Agent 燃速热力图 | ✅ |
| `SupervisionDecayChart.tsx` | 组件 | 重复场景人工监督衰减折线柱状图，直观展现多轮任务执行中人工介入率逐级衰减特征 | ✅ |
| `CoordinationFrictionScoreboard.tsx` | 组件 | 人机协调摩擦度量与监督衰减全景记分板、4 大关键 KPI 卡片与真实业务 ROI 战报看板 | ✅ |
| `cronDoctorTypes.ts` | 类型 | 定时任务舰队巡检、6 大防御门禁与外科手术式修复类型契约 | ✅ |
| `CronFleetHealthDeck.tsx` | 组件 | 定时任务舰队全景健康体态顶栏胶囊看板与静默故障隐患告警卡片 | ✅ |
| `CronDoctorReportDrawer.tsx` | 组件 | 定时任务隐患详情自查抽屉、修复指引与外科手术式快速治愈执行视窗 | ✅ |
| `deliveryBudgetTypes.ts` | 类型 | 多智能体整轮交付全生命周期成本核算、未知用量审计与硬预算熔断契约 | ✅ |
| `TrialLedgerBreakdownTable.tsx` | 组件 | 单次 Worker 尝试流水明细表，支持未知用量保守计提醒目提示与分类审计 | ✅ |
| `CumulativeDeliveryLedgerCard.tsx` | 组件 | 整轮交付全生命周期成本核算大盘、双账本聚合透视与硬预算保护熔断交互卡片 | ✅ |
| `agenticTrafficTypes.ts` | 类型 | AI Agent 流量识别、4 阶段漏斗与 AEO 静默审判诊断契约 | ✅ |
| `AgenticTrafficDeck.tsx` | 组件 | AI Agent 流量精准解构、活跃 Coding Agent 分布与 4 阶梯转化漏斗大盘 | ✅ |
| `AbandonmentAttributionView.tsx` | 组件 | 静默审判流失缺陷排行榜与页面 AEO 即时诊断透视组件 | ✅ |
| `sanitizedDebugTypes.ts` | 类型 | 零数据外泄物理脱敏诊断包、SHA256 签名与 48h 阅后即焚短链契约定义 | ✅ |
| `SanitizedDebugShareModal.tsx` | 组件 | 零外泄调试包导出与阅后即焚分享弹窗，支持抹除审计透视与 .myrmdiag 导出 | ✅ |
| `tokenEconomicsTypes.ts` | 类型 | 长任务 Token 经济学、99% 缓存节流真实收益与单位成本漂移契约定义 | ✅ |
| `CostDriftExplainerDrawer.tsx` | 组件 | 周期单位成本漂移感知与归因解释抽屉，展示历史基线对比与防刺客策略 | ✅ |
| `CacheSavingsRoiHUD.tsx` | 组件 | 99% 缓存节流真实收益大盘、实付与基线对比、算力燃速与熔断护航视窗 | ✅ |
| `deliveryDossierTypes.ts` | 类型 | 跨智能体交付证据卷宗、物理验证收据与分层资产摩擦度量契约定义 | ✅ |
| `DeliveryEvidenceDossierModal.tsx` | 组件 | 全链路交付证据卷宗弹窗，支持 5 大事实维度透视与 .dossier.json 导出 | ✅ |
| `HarnessEfficacyDeck.tsx` | 组件 | 跨智能体资产健康与效能大盘，按模型分层度量真实采纳率与摩擦刺客资产识别 | ✅ |
| `rateLimitGovernorTypes.ts` | 类型 | 客户端主动流量整形、响应头嗅探与子 Agent 切片配额 TypeScript 契约定义 | ✅ |
| `RateLimitGovernorHUD.tsx` | 组件 | 客户端主动限流预测阀门与自适应配额调度 HUD，多模型 RPM/TPM 水位与零 429 顺滑放行仪表盘 | ✅ |
| `SubagentQuotaAllocationDrawer.tsx` | 组件 | 子 Agent 隔离配额切片管理抽屉，提供动态削峰、切片熔断警示与一键重置窗口 | ✅ |
| `contextSavingsTypes.ts` | 类型 | 上下文拦截节流战报、每工具节省率与 7 维工程障碍模式 TypeScript 契约定义 | ✅ |
| `ContextSavingsWarReportModal.tsx` | 组件 | 上下文拦截节流战报弹窗，直观呈现每工具节流率、折算真金白银 (CNY/USD) 与 .savings.json 导出 | ✅ |
| `EngineeringInsightRoleDeck.tsx` | 组件 | 研发效能与工程障碍模式看板，按 CTO/EM/FinOps/DevOps 多角色切片展示瓶颈信号与治理建议 | ✅ |
| `reasoningSemanticsTypes.ts` | 类型 | 推理 Token 从属从契约、提供商口径归一化与零重复计数 TypeScript 契约定义 | ✅ |
| `ReasoningTokenIntegrityHUD.tsx` | 组件 | 推理 Token 计费语义诚实透视 HUD，展示从属层级结构、公式不变量与防双重计费守卫 | ✅ |
| `orgSpendLimitTypes.ts` | 类型 | 组织级月度 Agent 共享预算限额、硬熔断与 ident 身份归因 TypeScript 契约定义 | ✅ |
| `OrgSpendLimitDashboard.tsx` | 组件 | 组织共享预算仪表盘与用户归因排行看板，支持水位进度条、熔断报警与预检模拟台 | ✅ |
| `knowledgeCompoundingTypes.ts` | 类型 | 知识复利五大闭环指标、健康快照与微调试算 TypeScript 契约定义 | ✅ |
| `KnowledgeCompoundingScoreboard.tsx` | 组件 | 知识复利五大闭环指标全景记分板，支持雷达卡片网格、劣化告警与交互式模拟体检 | ✅ |
| `turnContextProvenanceTypes.ts` | 类型 | 逐轮上下文装配来源清单、SHA256 指纹快照与跨轮差异 TypeScript 契约定义 | ✅ |
| `TurnContextProvenanceAuditModal.tsx` | 组件 | 会话逐轮上下文注入来源清单与可复现审计弹窗，支持来源 Token 占比条、指纹复制与跨轮比对 | ✅ |
| `deploymentFunnelTypes.ts` | 类型 | 交付部署漏斗监测、阶段转化率、反馈情感与主动 Nudge 闭环 TypeScript 契约定义 | ✅ |
| `DeploymentFunnelDashboard.tsx` | 组件 | 交付部署漏斗监测与反馈闭环大盘，展示 4 阶梯转化、流失断点、反馈统计与一键目标派发 | ✅ |
| `streamMetricsTypes.ts` | 类型 | 流式调用按最终结果计量、防 Chunk 污染与会话时延 TypeScript 契约定义 | ✅ |
| `StreamMetricsCockpit.tsx` | 组件 | 流式调用最终结果计量驾驶舱，展示真实调用数、SLA 成功率、防虚高倍数与终态分布 | ✅ |
| `otelDegradeTypes.ts` | 类型 | OpenTelemetry 探针运行姿态、优雅降级与零硬依赖 TypeScript 契约定义 | ✅ |
| `OtelGracefulDegradeHUD.tsx` | 组件 | OpenTelemetry 探针零硬依赖与优雅降级 HUD，展示三态运行姿态、拦截统计与故障注入模拟 | ✅ |
| `diagnosticStreamTypes.ts` | 类型 | 运行流诊断事件解耦、严重度筛选与双轨隔离通道 TypeScript 契约定义 | ✅ |
| `RunStreamDiagnosticDrawer.tsx` | 组件 | 运行流诊断抽屉组件，实现诊断事件流与用户消息流物理分离，杜绝聊天气泡污染 | ✅ |
| `turnUsageTypes.ts` | 类型 | 回合级使用量双计数、Billed 账单与 Freeze 缓存状态对比 TypeScript 契约定义 | ✅ |
| `TurnBilledUsageDualCountHUD.tsx` | 组件 | 回合级 Billed Usage 双计数透视 HUD，可视化呈现累加账单与最新缓存状态分离及防虚增保护 | ✅ |
| `contextBreakdownTypes.ts` | 类型 | 上下文用量七分类占比、60%/90% 警戒线与双口径对账 TypeScript 契约定义 | ✅ |
| `ContextUsageBreakdownHUD.tsx` | 组件 | 上下文用量七分类透视与警戒线 HUD，提供真实注入分类、60%/90% 标尺与一键压缩交互 | ✅ |
| `localSinkTypes.ts` | 类型 | 本地盘可观测性落盘兜底状态、Spans 链路与控制回调 TypeScript 契约定义 | ✅ |
| `LoopForgeOtelOptionalDashboard.tsx` | 组件 | OpenTelemetry 缺失降级与本地盘兜底大盘，可视化呈现本地 JSONL 持久化与离线链路回放 | ✅ |
| `rateLimitSplitTypes.ts` | 类型 | 429 限流来源拆分与失败归因 TypeScript 契约定义 | ✅ |
| `RateLimitSourceSplitHUD.tsx` | 组件 | 限流来源拆分与失败归因 HUD，细分 myrm vs upstream 429、提供商失败分布与总数对齐校验 | ✅ |
| `enterpriseCreditCockpitTypes.ts` | 类型 | 企业级统一 Credit 池与人-时-数-险同链路审计 TypeScript 契约定义 | ✅ |
| `EnterpriseCreditAndRiskOpsCockpit.tsx` | 组件 | 企业用量与风险运营驾驶舱，展示全局 Credit 配额、各端分布及人-时-数-险同链路审计穿透 | ✅ |
| `unattendedReliabilityTypes.ts` | 类型 | 无人值守可靠性三联自证指标与运行事实 TypeScript 契约定义 | ✅ |
| `UnattendedReliabilityTriadHUD.tsx` | 组件 | 无人值守可靠性三联自证 HUD，展示重启续跑率、零重复副作用率、诚实上报率与一键验收测试 | ✅ |
| `customAgentInsightsTypes.ts` | 类型 | 自定义智能体洞察、意图聚类、技能漏斗健康度与人机卡点 ROI TypeScript 契约定义 | ✅ |
| `CustomAgentInsightsCockpit.tsx` | 组件 | 自定义智能体运营洞察驾驶舱，展示意图聚类分布、技能调用成功率/P95 延迟与 HITL 产出 ROI | ✅ |
| `evidenceCrossVerificationTypes.ts` | 类型 | 多源证据交叉验证、四分制置信度评级与排障定论 TypeScript 契约定义 | ✅ |
| `EvidenceCrossVerificationCockpit.tsx` | 组件 | 多源证据交叉验证与四分制置信度排障大盘，展示四维立体证据链、根因诊断与行动派修复补丁 | ✅ |
| `compositeUsageLedgerTypes.ts` | 类型 | 六维复合主键用量分摊账本与双轨对账状态 TypeScript 契约定义 | ✅ |
| `CompositeUsageLedgerHUD.tsx` | 组件 | 六维复合账本与双轨对账 HUD，展示本地估算 vs 实际扣费、细粒度 task 归因与账本流水 | ✅ |
| `ambientAuxiliaryAccountingTypes.ts` | 类型 | 环境感知式用量记账与任务维度精准归因 TypeScript 契约定义 | ✅ |
| `AmbientAuxiliaryAccountingHUD.tsx` | 组件 | 环境感知式用量记账 HUD，展示核心对话 vs 派生任务分摊、Prompt Cache 纯度隔离与快照流 | ✅ |
| `multimodalTraceTypes.ts` | 类型 | 多模态 Trace 媒体对象引用解耦与原位三步排查 TypeScript 契约定义 | ✅ |
| `MultimodalTraceViewerModal.tsx` | 组件 | 多模态 Trace 原位三步排查与媒体引用解耦大盘，支持 4 态可见性指示、原位预览与黄金样本加星锁 | ✅ |
| `sandboxHardwareTelemetryTypes.ts` | 类型 | 沙箱硬件资源动态遥测与三级阶梯熔断 TypeScript 契约定义 | ✅ |
| `SandboxHardwareTelemetryDashboard.tsx` | 组件 | 沙箱硬件资源遥测与失控三级熔断控制台，呈现 CPU/RAM/Disk 水位进度条、三级阶梯横幅、阈值调节与事故历史 | ✅ |
| `eventCausalityLineageTypes.ts` | 类型 | 事件驱动因果溯源、DAG 拓扑链路与反向文件归因 TypeScript 契约定义 | ✅ |
| `EventCausalityLineageDeck.tsx` | 组件 | 事件驱动因果溯源与动作归因图谱，展示因果链拓扑面包屑、决策认知动作流、修改产物与秒级反向文件归因 | ✅ |
| `visualFlightRecorderTypes.ts` | 类型 | 视觉故障黑匣子录制器与卡顿短循环切片回放 TypeScript 契约定义 | ✅ |
| `VisualFailureFlightRecorderModal.tsx` | 组件 | 视觉故障黑匣子与卡顿回放模态弹窗，支持 5fps 自动播放/暂停、滑动条与胶卷逐帧定位、10 秒破案根因标注 | ✅ |
| `dualDomainMeteringTypes.ts` | 类型 | 双域透明计量边界界定、三维穿透成本与财务合规对账 TypeScript 契约定义 | ✅ |
| `DualDomainMeteringCockpit.tsx` | 组件 | 双域透明计量驾驶舱，展示网关域 vs 沙箱域边界指示、三维穿透成本卡片、分摊比例条与 SHA-256 对账凭据 | ✅ |
| `crossPeriodMilestoneTypes.ts` | 类型 | 多智能体跨周期透视报表、成长等级每日任务与团队活跃度 TypeScript 契约定义 | ✅ |
| `MultiAgentCrossPeriodPivotDeck.tsx` | 组件 | 多智能体跨周期透视大盘，展示周/月/季度周期报表、按智能体堆叠消耗拆分、游戏化成长体系与团队拥抱度榜单 | ✅ |
| `metricCardinalityTypes.ts` | 类型 | 热点路径指标基数封顶、动态上限微调与溢出统计 TypeScript 契约定义 | ✅ |
| `MetricCardinalityCapHUD.tsx` | 组件 | 指标基数封顶与溢出守卫控制台，呈现各指标基数水位进度条、动态上限微调、溢出哨兵桶统计与 Top 标签分布 | ✅ |
| `codeFreshnessTypes.ts` | 类型 | 运行时代码新鲜度三态判定、进程时间戳对比与漂移 TypeScript 契约定义 | ✅ |
| `RuntimeCodeFreshnessHUD.tsx` | 组件 | 运行时代码新鲜度三态判定控制台，呈现整体新鲜度胶囊、受检模块列表、时钟漂移高亮与即时抽检 | ✅ |
| `runtimeZombieReaperTypes.ts` | 类型 | 智能体因果拓扑快照、孤儿进程收割与死锁熔断 TypeScript 契约定义 | ✅ |
| `AgentRuntimeCausalityCockpit.tsx` | 组件 | 原生活动监视器风格因果拓扑驾驶舱，呈现父子因果树、进程级资源消耗、一键孤儿收割与失败回溯 | ✅ |
| `delegationBillingTypes.ts` | 类型 | 外部委托用量透明化、订阅 vs API 计费分轨与节省额度 TypeScript 契约定义 | ✅ |
| `DelegationBillingTransparencyBadge.tsx` | 组件 | 计费口径分轨徽标组件，直观展示订阅额度消耗（不计费）vs API 计费、来源后端与预估节省额 | ✅ |
| `auditTheaterTypes.ts` | 类型 | 用户面审计剧场、动作时间线与数据访问台账 TypeScript 契约定义 | ✅ |
| `InConversationAuditTheaterDeck.tsx` | 组件 | 对话内权威审计剧场与数据访问台账组件，提供双 Tab 动作时间线/数据台账与撒谎免疫认证 | ✅ |
| `memoryBackendMetricsTypes.ts` | 类型 | 记忆多后端与召回细分阶段维度指标、P50/P95 延迟与 Opt-in 配置 TypeScript 契约定义 | ✅ |
| `MemoryBackendMetricsDashboard.tsx` | 组件 | 记忆多后端与召回细分阶段性能大盘，支持 SQLite FTS5 vs Qdrant vs In-Memory 横向对比与高基数 Opt-in 切换 | ✅ |
| `abortedUsageLedgerTypes.ts` | 类型 | 中止辅助模型调用账本、未知用量状态与风险统计 TypeScript 契约定义 | ✅ |
| `AbortedAuxiliaryUsageHUD.tsx` | 组件 | 辅助调用用量与未知防虚假免费守护 HUD，严禁中止未报告调用显示 0 Token，直观暴露潜在财务风险 | ✅ |
| `activeSkillTelemetryTypes.ts` | 类型 | 活跃技能 Span 遥测记录、ContextVar 属性注入与 P95 聚合 TypeScript 契约定义 | ✅ |
| `ActiveSkillSpanTelemetryCockpit.tsx` | 组件 | 活跃技能 Span 遥测全景驾驶舱，透传 myrm.skill.active 属性、展示各技能 P95 延迟与故障归因 | ✅ |
| `durableBudgetLedgerTypes.ts` | 类型 | 持久化每日预算账本、丢弃分支差额与会话实际账单 TypeScript 契约定义 | ✅ |
| `DurableBudgetLedgerHUD.tsx` | 组件 | 持久化每日预算恢复 HUD，从持久账本恢复真实花费，防止消息重试/删除导致预算低估击穿 | ✅ |
| `unattendedCoverageTypes.ts` | 类型 | 无人值守与多渠道运行事件日志覆盖状态与分片健康 TypeScript 契约定义 | ✅ |
| `UnattendedEventLogCoverageHUD.tsx` | 组件 | 无人值守与多渠道事件日志覆盖全景大盘，呈现 Cron/Channel/Goal/Voice 统一注入与按日分片防无限增长指标 | ✅ |
| `index.ts` | 门面 | 聚合导出模块内所有组件与类型定义 | ✅ |



