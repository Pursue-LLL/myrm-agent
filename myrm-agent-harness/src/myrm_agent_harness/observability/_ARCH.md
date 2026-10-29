# observability/

## Overview
Observability tools for Myrm Agent framework. Provides Prometheus metrics, auth failure detection, active health diagnostics, and request tracing context for log correlation.

**Naming disambiguation** (same word, different packages — do not merge or relocate):

| Path | Responsibility |
|------|----------------|
| **`myrm_agent_harness.observability`** (this package) | Metrics, health probes, ContextVar log tracing |
| `myrm_agent_harness.agent.streaming.broadcast` | Chat tool SSE (`ToolBroadcastBus`) |
| `myrm_agent_harness.infra.pubsub` | Server business SSE (`PubSubBus`) |
| `myrm_agent_harness.infra.tracing` | **OpenTelemetry** distributed tracing (optional `[observability]` extra) |
| `toolkits/*/observability.py` | Per-toolkit business-neutral operation DTOs |

`toolkits/` may depend on this package per [toolkits/_ARCH.md](../toolkits/_ARCH.md) Allowed Dependencies.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Observability tools — auth detection, tracing primitives re-export. | ✅ |
| auth_detector.py | Core | Authentication failure detection for circuit breaker logic. | ✅ |

| Submodule | Description |
|-----------|-------------|
| audit_trail/ | Dual-track audit log, redaction, and compliance dossiers. |
| digest/ | Health evaluation digest. |
| metrics/ | Generic metrics utilities; Prometheus counters require `[observability]` extra (NoOp fallback otherwise). |
| diagnostics/ | Framework-level self-inspection — health probes (incl. gateway runtime vitals), benchmark hook registry, and diagnostic protocol. |
| thought_telemetry/ | 长推理思考链（CoT）流式遥测与失控死循环守护子包：毫秒耗时度量、自纠偏步骤特征识别、N-gram 死循环熔断与软中断纠偏。 |
| timeline_visualizer/ | 任务执行透视镜与技能调用时序可视化核心引擎：毫秒级耗时追踪、时序瀑布流、步骤状态树与插嘴打断。参见 [timeline_visualizer/_ARCH.md](timeline_visualizer/_ARCH.md)。 |
| tracing/ | ContextVar-based request tracing (trace_id / session_id) with logging.Filter and JSON formatter. |
| context_retrieval/ | 上下文分层检索下钻决策树追踪与剪枝留痕套件：目录递归下钻、分值比对、动态阈值剪枝判定与检索全景轨迹快照。参见 [context_retrieval/_ARCH.md](context_retrieval/_ARCH.md)。 |
| diagnostics_bundle/ | 端内沙箱现场全景诊断打包与自愈凭证引擎：生命体征抓取、PII/Secret 深度脱敏与防篡改 HMAC 校验和。参见 [diagnostics_bundle/_ARCH.md](diagnostics_bundle/_ARCH.md)。 |
| coordination_friction/ | 人机协调摩擦度量、人工介入衰减曲线与协同效率 ROI 量化记分板引擎：HITL 介入密度统计、多轮监督衰减曲线与注意力时间净节省折算。参见 [coordination_friction/_ARCH.md](coordination_friction/_ARCH.md)。 |
| cron_doctor/ | Cron 自动化任务舰队全景健康体检医生与预防性隐患自查引擎：6 大健康门禁只读扫描（执行/交付/回执/调度逾期/脚本/工作区）、隐患聚合诊断与外科手术式修复指引。参见 [cron_doctor/_ARCH.md](cron_doctor/_ARCH.md)。 |
| sanitized_debug_dump/ | 一键安全脱敏诊断包生成、敏感凭据物理抹除与加密阅后即焚分享管理包：Zero-Leak 正则抹除、环境体征快照与 48h/3次自毁分享短链。参见 [sanitized_debug_dump/_ARCH.md](sanitized_debug_dump/_ARCH.md)。 |
| delivery_dossier/ | 跨智能体任务交付证据卷宗、资产真实有效性与摩擦浪费可观测性引擎：5大维度不可变交付证据（Spec/指纹/工具/物理凭证/验收）、分层资产效能度量与摩擦刺客资产识别。参见 [delivery_dossier/_ARCH.md](delivery_dossier/_ARCH.md)。 |
| rate_limit_governor/ | 客户端主动限流预测阀门、按模型动态配额自适应调度与零 429 顺滑放行引擎：多厂商响应头侦听、前置微延迟平滑削峰 (200~500ms) 与多并发子任务配额切片隔离。参见 [rate_limit_governor/_ARCH.md](rate_limit_governor/_ARCH.md)。 |
| org_spend_limit/ | 团队共享智能体组织月度限额、逐 Query 标签归因与超限熔断套件：群聊/私信分级记账、80% 软预警与 100% 硬限额熔断、按身份/Surface 审计归因。参见 [org_spend_limit/_ARCH.md](org_spend_limit/_ARCH.md)。 |
| knowledge_compounding/ | 知识复利健康度记分板与五大指标闭环套件：统一只读聚合重复错误率、知识命中率、人工纠正次数、任务一次通过率、过期知识占比，提供复利层级判定与劣化报警检测。参见 [knowledge_compounding/_ARCH.md](knowledge_compounding/_ARCH.md)。 |
| turn_context_provenance/ | 会话逐轮上下文注入来源清单、内容指纹快照与可复现审计套件：记录 System Prompt、Memory、Skill、MCP、Workspace File 注入清单、计算 SHA256 指纹与跨轮差异比对。参见 [turn_context_provenance/_ARCH.md](turn_context_provenance/_ARCH.md)。 |
| stream_metrics/ | 流式调用按最终结果计量核心套件：杜绝中间 chunk 计数污染、按终态结果（SUCCESS/ERROR/CANCELLED/TIMEOUT）归因、TTFT 首字时延度量与防虚高膨胀统计。参见 [stream_metrics/_ARCH.md](stream_metrics/_ARCH.md)。 |
| diagnostic_stream/ | run-stream 协议诊断事件分离与正常消息流解耦套件：双轨物理隔离正轨用户消息与旁路诊断告警，提供 ACP 会话 Hook 与多维分类统计。参见 [diagnostic_stream/_ARCH.md](diagnostic_stream/_ARCH.md)。 |
| context_breakdown/ | 上下文用量七分类精准解析与 60%/90% 警戒线判定核心架构：识别真实注入标签，消除余量黑盒，支持估算与提供商实报并列对比。参见 [context_breakdown/_ARCH.md](context_breakdown/_ARCH.md)。 |
| rate_limit_split/ | 限流来源拆分与失败归因套件：429 按自身限流 (myrm) 与上游拒绝 (upstream) 拆分，失败按模型厂商 (provider) 打标，未打标总数严格保持不变。参见 [rate_limit_split/_ARCH.md](rate_limit_split/_ARCH.md)。 |
| enterprise_credit_cockpit/ | 企业用量与风险运营驾驶舱引擎：统一企业 Credit 池跨端治理、人-时-数-险同链路审计留痕与穿透式治理大盘。参见 [enterprise_credit_cockpit/_ARCH.md](enterprise_credit_cockpit/_ARCH.md)。 |
| unattended_reliability/ | 无人值守可靠性三联自证套件：量化与自证重启续跑率、重复执行零副作用率与阻塞如实上报率，杜绝幻觉伪成功，支持一键复现验收跑分。参见 [unattended_reliability/_ARCH.md](unattended_reliability/_ARCH.md)。 |
| agent_insights/ | 自定义智能体运行洞察套件：面向 Agent 视角的意图与场景聚类分布、技能调用健康与耗时漏斗、以及 HITL 卡点率与 Token 产出比分析。参见 [agent_insights/_ARCH.md](agent_insights/_ARCH.md)。 |
| evidence_cross_verification/ | 多源证据交叉验证与四分制置信度根因排查套件：静态代码、分布式 Trace、运行时日志与知识库历史四维立体现证，四分制置信度推导与行动派修复补丁交付。参见 [evidence_cross_verification/_ARCH.md](evidence_cross_verification/_ARCH.md)。 |
| sandbox_hardware_telemetry/ | 多维度沙箱硬件资源动态遥测与三级阶梯式失控死循环自动熔断器套件：CPU/RAM/Disk/Network 秒级度量采样、三级阶梯自愈拦截 (80% 预警 ➔ 90% 挂起 ➔ 95% 硬熔断) 与现场事故历史。参见 [sandbox_hardware_telemetry/_ARCH.md](sandbox_hardware_telemetry/_ARCH.md)。 |
| event_causality_lineage/ | 事件驱动全链路因果溯源时间线、动作归因图谱与审计白盒透视套件：外部触发事件 (GitHub/Slack/MCP/Cron) ➔ 规则匹配 ➔ Agent动作决策 ➔ 产出Diff全链路DAG，与毫秒级反向文件变更归因追溯。参见 [event_causality_lineage/_ARCH.md](event_causality_lineage/_ARCH.md)。 |
## Key Dependencies

- `toolkits` (via diagnostics probes)
