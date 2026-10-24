# api/agents/

## 架构概述

Agent 产品 HTTP 层：用户自定义智能体 CRUD、GeneralAgent 流式对话入口、子 Agent 预设、Provider 配置、OpenAPI 服务发现与沟通风格目录。上级：[../_ARCH.md](../_ARCH.md) · 流式核心：[general_agent/_ARCH.md](general_agent/_ARCH.md) · 沟通风格目录：[personality/_ARCH.md](personality/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | AI Agent API 模块 | ✅ |
| `_optional_routers.py` | 路由 | Agent 可选路由挂载表：自治循环、多 Bot、团队编组等依赖 harness 同名模块，缺失时按功能粒度跳过并告警。 | ✅ |
| `agent.py` | 核心 | Agent 核心 CRUD、快照/回滚、Avatar 上传、文件服务。创建与更新前，档案里模型会读的文字（`system_prompt`、`description`、建议提示词、命令绑定的指令）经 `reject_if_risky` 过闸，命中返回 400 `risk_held`、不落库；责任单元的 `responsibility_scope` / `acceptance_criteria` 只用于治理展示，不过闸。 | ✅ |
| `_agent_response.py` | 内部 | AgentProfile → AgentResponse 序列化工具函数（被 agent/portability/templates 共享）。 | ✅ |
| `agent_extras.py` | 核心 | Agent 辅助端点：Secrets CRUD、使用统计、动作空间 ASCS 评估与 Turn1 技能目录预览（元数据经 `runtime_metadata.skill_to_runtime_metadata` 适配，技能可用性与 Agent runtime 共用 `requirements_availability` 判定）。 | ✅ |
| `agent_portability.py` | 核心 | Agent 可移植性：克隆、Marketplace 跨沙箱分发（导出/导入）。专家之间交换只走 Agent Plugins ZIP（`/plugins/export`、`/plugins/import`），JSON 导入导出与工作区文件束已退役。 | ✅ |
| `agent_history.py` | 模块 | Get the version history of an agent's profile. | ✅ |
| `ai_build.py` | 模块 | AI-driven agent config generator: accepts a natural-language intent, streams a complete AgentCreate-compatible JSON (name, prompt, skills, MCPs, tools); without a usable model it refuses with 422 `{message, error_code: model_not_configured}` so the client can localize it; the intent is screened by the risk gate before the model is resolved (400 `risk_held`); the skill catalog offered to the model lists the installed skills whose dependencies are met (`Skill.available`) | ✅ |
| `generate_prompt.py` | 模块 | Thin API for the agent editor: resolves the user's default model and streams a draft system prompt; the intent and the existing prompt to refine are screened by the risk gate first (400 `risk_held`) | ✅ |
| `openapi_services.py` | 模块 | OpenAPI Services API. | ✅ |
| `providers.py` | 模块 | Agent provider configuration endpoints for deletion impact analysis and batch operations | ✅ |
| `subagents.py` | 模块 | Subagent REST：list / cancel-all / steer / cancel；registry merge via harness session_tree；steer 的消息先过风险闸门（`reject_if_risky`，命中 400 `risk_held`，不送达子智能体）。 | ✅ |
| `suggestions.py` | 模块 | Generate follow-up question suggestions using the filter model. | ✅ |
| `fleet_overview.py` | 模块 | Agent Fleet Overview — 按 agent_id 聚合月度 Token/Cost、Cron 数、待审批数（goal 审批 + kanban IN_REVIEW 按 agent 分组）、实时运行状态的 KPI 端点，供 /agents 页面 Fleet 视图使用。零新表，纯读聚合。 | ✅ |
| `fleet_telemetry.py` | 路由 | 分布式机队六态健康遥测与配额诊断 API 端点：提供 `POST /fleet/diagnose`（五级渐进自省探针排障）与 `GET /fleet/health-summary`（六态分布概览）。 | ✅ |
| `templates.py` | 模块 | Agent template catalog and factory. | ✅ |
| `subagent_presets/` | 子包 | 只读子代理预设目录 `GET /agents/subagent-presets`：返回 Agent 编辑器可绑定的内置专家元数据（id/名称/描述/依赖 builtin tool），不返回 system prompt。 | ✅ |
| `personality/` | 子包 | 通信风格目录（只读）：`GET /agents/personalities` 返回 17 个预置风格的中英双语名称/描述/示例回复、GUI 图标标识与分类。目录本体在 `ai_agents/personality_templates.py`，本子包只做序列化，前端不再维护第二份风格清单。 | ✅ |
| `profile_audit.py` | 模块 | Agent Profile security audit: POST /{agent_id}/audit — deterministic risk scoring via harness profile_audit engine. | ✅ |
| `readiness.py` | 模块 | Per-agent readiness dry-run: GET /{agent_id}/readiness + POST /{agent_id}/readiness/invalidate — 6-dimension config readiness check. | ✅ |
| `governance.py` | 模块 | Responsibility-unit governance: GET /governance/overview（孤儿/重叠只读巡检，零 LLM）+ POST /governance/merge/dry-run + POST /governance/merge/execute（快照→并配置→重绑定时/渠道→删来源复用级联）。 | ✅ |
| `agent_assembler_router.py` | 路由 | 智能体可视化装配器 REST API：提供积木依赖体检 `/assembler/validate`、微沙箱即时演练 `/assembler/dry-run` 与 6 大能力积木池 `/assembler/block-catalog`。 | ✅ |
| `agent_avatar_router.py` | 路由 | 智能体头像生成与锁定 REST API：提供纯确定性多风格 SVG 种子生成 `/avatar/generate-svg`、AI 生图代理 `/avatar/generate-ai` 与智能体头像锁定持久化 `/{agent_id}/avatar`。 | ✅ |
| `memory_hub_router.py` | 路由 | 智能体记忆资产中心与细粒度 ACL 授权 REST API：提供四大类资产检索/创建 `/memory-hub/assets`、ACL 策略变更 `/memory-hub/assets/{id}/acl`、以及智能体 4 槽位装备装配与卸载 `/agents/{agent_id}/equipment`。 | ✅ |
| `agent_multiplexer_router.py` | 路由 | 智能体会话多路复用器 REST API：提供多并发持久会话列表 `/multiplexer/sessions`、互视日志快照 `/sessions/{id}/inspect` 与指导注入 `/sessions/{id}/instruct`。 | ✅ |
| `topology_pruning_router.py` | 路由 | 模型能力感知拓扑修剪 REST API：提供任务自适应拓扑修剪评估 `/topology/prune-evaluation` 与模型阶梯目录查询 `/topology/tiers`。 | ✅ |
| `agent_handoff_router.py` | 路由 | 跨智能体移交与对话内任务委派 REST API：提供对话内委派卡片创建 `/handoff/in-chat`、五阶段生命周期推进 `/handoff/in-chat/{id}/advance-stage`、审批闸门与行内 CTA `/handoff/in-chat/{id}/action`、以及底层备忘录管理。 | ✅ |
| `todo_store_router.py` | 路由 | 跨进程/跨插件共享 Todo 计划声明存储与安全 HUD 投影 REST API：提供计划项增删改查 `/todo-store/{session_id}/items` 与防 ANSI 注入的轻量 HUD 投射 `/todo-store/{session_id}/hud`。 | ✅ |
| `agent_hierarchy_router.py` | 路由 | 智能体创建层级树与血统溯源 REST API：提供多智能体树状层级森林目录 `/hierarchy/tree`、创建来源元数据注册 `/hierarchy/provenance` 与指定 Agent 溯源路径查询 `/{agent_id}/provenance`。 | ✅ |
| `split_session_goal_router.py` | 路由 | 交付与规划双阶段流转 Goal 模版 REST API：提供内置双窗口 Goal 模版目录查询 `/split-session-goals/templates`、实例创建与获取、生命周期阶段推进 `/split-session-goals/{id}/advance-stage` 与终态流转。 | ✅ |
| `ralph_workflow_router.py` | 路由 | Ralph 式 Fresh-Agent 多轮循环 REST API：提供每轮启动无历史全新子 Agent 会话创建 `/ralph-loop/sessions`、轮次状态查询与五字段结构化交接推进 `/ralph-loop/sessions/{id}/advance-round`。 | ✅ |
| `infra_quota_router.py` | 路由 | 每用户/组织多 Agent 基础设施配额治理 REST API：提供四大核心维度（活跃 Agent、临时 DB、并发沙箱、Volume 存储）用量查询 `/infra-quota/overview`、自助 Provision 准入门禁核验 `/infra-quota/check`（Fail-Closed）与配额调整。 | ✅ |
| `advisor_channel_router.py` | 路由 | 双模型军师实时异步独立审查频道 REST API：提供单步审查评估 `/advisor/review`（aside/concern/blocker 三级干预判定与熔断触发）、审查历史查询与状态清理。 | ✅ |
| `subagent_hub_router.py` | 路由 | 子代理实时监管抽屉 REST API：提供会话级花名册全景与成本概览查询 `/chats/{chat_id}/subagents/hub/roster`、单 Worker 实时执行轨迹读取 `/chats/{chat_id}/subagents/{task_id}/transcript` 与单点干预控制 `/chats/{chat_id}/subagents/{task_id}/action`（Steer/Kill/Revive）。 | ✅ |
| `conflict_gate_router.py` | 路由 | 多 Bot 并行产出冲突对账与合并前拦截门 REST API：提供并行 Worker 写集碰撞评估 `/chats/{chat_id}/conflicts/evaluate`（Hash 碰撞阻断合并）、待对账冲突列表 `/chats/{chat_id}/conflicts` 与对账解决端点 `/chats/{chat_id}/conflicts/{conflict_id}/resolve`。 | ✅ |
| `mcp_scope_gate_router.py` | 路由 | 数字员工 MCP 工具作用域隔离门禁 REST API：提供 Profile 级 MCP 白名单策略配置 `/agents/{agent_id}/mcp-scope/policy`、动态发现候选工具物理裁剪过滤 `/agents/{agent_id}/mcp-scope/filter-discovered` 与单次工具调用鉴权 `/agents/{agent_id}/mcp-scope/verify-call`（Fail-Closed 403 拦截）。 | ✅ |
| `agent_operations_router.py` | 路由 | Agent-Owned 多智能体协同操作 REST API：提供 Agent 专属上下文注册 `/agents/operations/register`、List-form 花名册全景查询 `/agents/operations/roster`、专属隔离错误栈 `/agents/operations/{agent_id}/errors` 与能力白名单对齐校验 `/agents/operations/{agent_id}/resolve-capability`。 | ✅ |
| `durable_dispatch_router.py` | 路由 | Hermes Fabric 确定性远程分发与持久化对等日志 REST API：提供工作契约签发 `/chats/{chat_id}/remote-dispatch/prepare`、执行前 Fail-Closed 策略重核验 `/{dispatch_id}/revalidate-policy`、有界证据准入 `/{dispatch_id}/evidence`、单调递增对等日志链查询 `/{dispatch_id}/journal` 与崩溃后幂等自愈规划 `/{dispatch_id}/recovery`。 | ✅ |
| `report_fifo_router.py` | 路由 | Subagent 主动回报唤醒与严格有序结算 FIFO REST API：提供命名子智能体声明注册 `/chats/{chat_id}/report-fifo/register`、主动回报唤醒 `/chats/{chat_id}/report-fifo/report`、严格保序结算通知 `/chats/{chat_id}/report-fifo/settlement`、父 Step 边界批量排空 `/chats/{chat_id}/report-fifo/drain` 与队列全景概览 `/chats/{chat_id}/report-fifo/status`。 | ✅ |
| `failure_facts_router.py` | 路由 | 子智能体脱敏结构化失败事实与安全归因诊断协议 REST API：提供单行标准化安全诊断 Header 格式化与归因自愈建议 `/chats/{chat_id}/subagents/diagnose-failure`、4096 字节有界历史全景 `/chats/{chat_id}/subagents/failure-facts` 与会话清理端点。 | ✅ |
| `debate_workroom_router.py` | 路由 | 多智能体动态协同工作间与辩论流任务看板联动 REST API：提供工作间创建 `/chats/{chat_id}/debate-workrooms`、Leader 任务拆解 `/decompose`、专员发言质询 `/argument`、阶段流转 `/advance-phase`、共识收敛 `/converge` 与 Kanban 看板任务双向状态绑定同步 `/kanban-sync`。 | ✅ |
| `external_agent_bridge_router.py` | 路由 | 多源异构 Agent 外部进程桥接与 CLI 工具适配器 REST API：提供外部 Agent 注册与管理 `/agents/external-bridge/agents`、健康探针校验 `/probe`、进程同步执行 `/execute` 与 SHA-256 不可篡改执行凭证查询 `/receipts`。 | ✅ |
| `debate_synthesis_router.py` | 路由 | 分层 Leader 自动任务分治、专员调研质询与决策权衡对比矩阵收敛 REST API：提供工作流创建 `/chats/{chat_id}/debate-synthesis`、Leader 自动子任务 DAG 分解 `/decompose`、专员提案提交 `/proposals`、交叉辩论推进 `/advance-debate` 与多维度权衡对比矩阵收敛 `/synthesize`。 | ✅ |
| `agent_teams_router.py` | 路由 | Durable Agent Teams 隐式 Root Lead、kebab-case 具名成员名册、CAS 版本化共享任务板与对等邮箱 REST API：提供团队全景投影 `/teams/{team_id}/projection`、成员增查与失败报告 `/teams/{team_id}/members`、任务板 CRUD 与 CAS 乐观锁认领/流转 `/teams/{team_id}/tasks`、对等发信与收件箱排空 `/teams/{team_id}/messages` 与边沿事件变更监听 `/teams/{team_id}/wait`。 | ✅ |
| `adaptive_wakeup_router.py` | 路由 | 后台长任务与子智能体完成自适应唤醒宿主驱动器与有界轮次熔断保护 REST API：提供会话唤醒配额查询 `/agents/adaptive-wakeup/sessions/{session_id}/budget`、人类输入重置 `/human-turn`、用户主动停止 `/stop`、结算路由裁决 `/settlements` 与暂存注入事件查询 `/injected`。 | ✅ |
| `subagent_scaling_router.py` | 路由 | 子任务并发与工具预算弹性扩容及无损平滑迁移 REST API：提供无损配置升级迁移 `/agents/subagents/scaling/migrate-config`、80% 动态水位心跳监控 `/watermark-heartbeat`、会话预警列表与一键扩容/解除。 | ✅ |
| `review_loop_router.py` | 路由 | 多视角并发子智能体评审与有界自愈复审闭环 REST API：提供三视角评审启动 `/chats/{chat_id}/review-loops/start`、有界轮次推进与自愈代码验证 `/{loop_id}/advance`、单环全景查询与会话清理。 | ✅ |
| `bot_mode_router.py` | 路由 | 具名智能体工位花名册、Bot-to-Bot @mention 寻址投递信箱中继 REST API：提供 AI 同事工位注册 `/chats/{chat_id}/bot-mode/register`、工位花名册全景查询 `/roster`、工位状态更新 `/bots/{bot_id}/status`、点对点信箱发信 `/messages/send`、@mention 扫描分发 `/messages/dispatch-mentions`、收件箱管理与已读标记。 | ✅ |
| `squad_composition_router.py` | 路由 | 总编排智能体自动组队、Model 留白两阶段向导与动态算力预算切分 REST API：提供高层任务自动组队蓝图生成 `/chats/{chat_id}/squad-composition/compose`、蓝图详情与全景查询 `/blueprints`、Phase-2 模型留白用户选型物化 `/materialize`、活跃战队查询与状态重置。 | ✅ |
| `failure_policy_router.py` | 路由 | 子智能体 mid-task 失败 per-role 重启/升级/跳过声明式策略 REST API：提供角色失败自愈策略注册 `/chats/{chat_id}/failure-policy/roles`、自愈策略清单查询、mid-task 故障自愈评估 `/evaluate-failure`、重试计数器重置与自愈历史全景。 | ✅ |
| `workspace_blueprint_router.py` | 路由 | 按项目/工作区自动复用团队 Blueprint 绑定与解析 REST API：提供工作区绑定团队蓝图 `/workspaces/{workspace_id}/blueprints`、活跃蓝图解析 `/active`、使用记录 `/record-usage`、解绑与全量绑定目录查询。 | ✅ |
| `scope_guardrails_router.py` | 路由 | Orchestrator 越权防护与安全建队模式收敛审核 REST API：提供蓝图角色权限审查 `/chats/{chat_id}/scope-guardrails/audit`、安全配置查询 `/config`、会话自定义规则更新与重置端点。 | ✅ |
| `autonomous_loop_router.py` | 路由 | Goal/Kanban 驱动自主编排循环与步数看门狗 REST API：提供自主循环启动 `/chats/{chat_id}/autonomous-loop/start`、实时状态查询 `/state`、单步自律推进 `/advance`、模式切换 `/mode` 与目标终态标记 `/complete`。 | ✅ |
| `creator_mode_router.py` | 路由 | 自然语言创造模式预设合成、沙盒防御校验与多端漫游 REST API：提供预设自省组装 `/agents/creator-mode/synthesize`、沙盒正反向防御检验 `/verify-sandbox`、多端同步漫游 `/roaming-sync` 与漫游记录目录 `/records`。 | ✅ |
| `tri_role_router.py` | 路由 | 规划-执行-可扩展评估三权分立与跨会话工件无损交接管线 REST API：提供会话创建与状态查询 `/chats/{chat_id}/tri-role/sessions`、阶段提交 `/stages/{stage_id}/plan` / `/generate` / `/evaluate`、阶段推进 `/advance` 与 Manifest 导出/恢复 `/manifest` / `/manifest/restore`。 | ✅ |
| `skill_bundle_router.py` | 路由 | 技能包清单化一键批量加载与运行时生命周期预热管理器 REST API：提供场景化技能包列表/注册/获取 `/skills/bundles`、预热探针诊断 `/{bundle_id}/warmup`、会话一键激活 `/chats/{chat_id}/skill-bundles/activate`、解绑与活跃状态查询。 | ✅ |
| `multi_bot_focus_router.py` | 路由 | 多Bot协同会话Mention焦点动态绑定与长会话防抖压实引擎 REST API：提供视口焦点上报与焦点查询 `/chats/{chat_id}/multi-bot/focus`、上下文压实防抖评估与完成记录 `/compaction/evaluate` / `/record`、流式任务卡片心跳与超时废弃清理 `/streams/heartbeat` / `/prune` / `/complete`。 | ✅ |
| `mcp_payload_summarizer_router.py` | 路由 | 重 Payload MCP/大文档获取专用子 Agent 预置与结构化摘要防污染 REST API：提供大 Payload 结构化压缩摘要提取 `/agents/mcp-summarizer/summarize`、未隔离直接注入污染审计诊断 `/agents/mcp-summarizer/diagnose` 与专用预置子 Agent 规范查询 `/agents/mcp-summarizer/preset`。 | ✅ |
| `coding_wave_router.py` | 路由 | 编码型 Agent Profile 可选预置与多阶段 Wave 波次流水线编排 REST API：提供波次会话初始化 `/chats/{chat_id}/coding-wave/sessions`、状态查询 `/progress`、任务状态更新 `/tasks/update`、严格门禁阶段推进 `/advance`、导出 orchestration_progress.json `/export-json` 与官方预置规范 `/agents/coding-wave/preset`。 | ✅ |
| `subagent_lifecycle_router.py` | 路由 | 原生 Subagent 细粒度生命周期管控工具链 REST API：提供独立子 Agent 派发 `/chats/{chat_id}/subagents/spawn`、异步等待汇总 `/wait`、状态列表查询 `/subagents`、运行中纠偏消息注入 `/input`、硬熔断终止 `/kill` 与演练完成接口。 | ✅ |
| `mixed_fleet_router.py` | 路由 | 混合舰队（Local Brain + Remote Executor）预置 REST API：提供混合舰队健康快照 `/chats/{chat_id}/mixed-fleet/snapshot`、Local Brain 任务交接派发 `/dispatch`、远端结果同步 `/sync`、执行完成/失败上报与心跳遥测 `/heartbeat`。 | ✅ |
| `zero_token_contract_router.py` | 路由 | 舰队可视化零 Token 契约 REST API：提供运行时确定性事件镜像摄取 `/chats/{chat_id}/zero-token/mirror` 与 `/mirror-batch`、Doctor LLM 调用拦截鉴权 `/check-llm`、零 Token 审计报告 `/audit`、违规演练测试 `/simulate-violation` 与账本重置 `/reset`。 | ✅ |
| `cross_surface_bridge_router.py` | 路由 | 跨界面智能体活动对话汇入桥 REST API：提供外源活动事件汇入 `/chats/{chat_id}/activity-bridge/ingress` 与 `/ingress-batch`、Fleet Canvas 投影快照查询 `/projection`、陈旧 presence 清理 `/prune-stale` 与账本重置 `/reset`。 | ✅ |
| `multi_lane_router.py` | 路由 | Pi Harness v2 会话内多 Lane 并行执行与共享追加树 REST API：提供 Lane 创建 `/chats/{chat_id}/multi-lane/lanes`、全景快照 `/snapshot`、共享树节点追加 `/lanes/{lane_id}/nodes`、操作派发 `/lanes/{lane_id}/dispatch`（严格 409 互斥防并发）、完成 `/complete`、取消 `/cancel` 与操作日志查询 `/lanes/{lane_id}/oplog`。 | ✅ |
| `session_fork_router.py` | 路由 | Pi Harness v2 确定性子会话派生与安全重放重接 REST API：提供确定性 childSessionId 纯计算 `/agents/session-fork/derive-id`、子会话 Fork 或 Safe Replay 重接 `/fork`、单子会话链接状态查询 `/children/{child_id}`、复制历史节点查看 `/nodes`、父会话下子会话目录查询 `/parents/{parent_id}/children` 与重置 `/reset`。 | ✅ |
| `token_budget_governance_router.py` | 路由 | 单模型多 Agent 共享上下文 Token 预算治理与路由开销可视化 REST API：提供角色配额声明与注册 `/chats/{chat_id}/token-governance/roles`、扇出前预算预检 `/precheck`、消费归集 `/consumption`、预算大盘全景快照 `/snapshot`、Doctor Nudge 警报查询 `/doctor-nudges` 与重置 `/reset`。 | ✅ |
| `pipeline_integrity_router.py` | 路由 | 开源可 inspect 工作流 · Handoff/Approval/Delivery 断点 Lint 与 Doctor 告警诊断 REST API：提供流水线断点 Lint 分析 `/agents/pipeline-integrity/lint`、一键自动治愈修复 `/auto-heal`、可审查决策链提取 `/inspect-chain`、典型参考流水线样例获取 `/samples` 与诊断报告缓存查询 `/reports/{pipeline_id}`。 | ✅ |
| `specialist_summoning_router.py` | 路由 | 对话流自然语言/@召唤子专家协同与上下文结构化汇聚 REST API：提供专家名册获取 `/agents/specialists/catalog`、特定专家详情 `/{specialist_id}`、意图感知与 @ 召唤检测 `/detect-intent`、沙箱隔离专家任务分发 `/chats/{chat_id}/specialists/summon` 与会话历史执行卡片查询/清理 `/executions`。 | ✅ |
| `swarm_mesh_router.py` | 路由 | SwarmForge 动态 Agent 集群拓扑编排器与多智能体网格通信 REST API：提供当前拓扑全景查询 `/agents/swarm-mesh/topology`、拓扑新建 `/create`、动态无损布局切换 `/switch`、节点弹性扩缩容 `/scale`、单节点带状态热迁移 `/migrate`、P2P 消息总线单播/组播/广播 `/messages`、以及共享黑板事实读写 `/blackboard`。 | ✅ |
| `workspace_inheritance_router.py` | 路由 | 工作区上下文继承与提示词编织 REST API：提供工作区规范多级发现 `/agents/workspace-inheritance/inspect-rules`、基于角色与 Token 预算的 Prompt 编织 `/agents/workspace-inheritance/enrich-prompt`、以及各会话继承审计历史全景 `/agents/workspace-inheritance/audit-history`。 | ✅ |
| `replay_dedup_router.py` | 路由 | 多智能体历史工具调用回放合并与状态机同步增强 REST API：提供连续等幂/只读工具调用聚合 `/agents/replay-dedup/merge-history`、单调状态流转 `/agents/replay-dedup/status-sync`、租约看门狗超时防假死自愈 `/agents/replay-dedup/watchdog-check` 与会话状态快照查询 `/{session_id}/statuses`。 | ✅ |
| `cloud_edge_relay_router.py` | 路由 | 云端-本地混合沙箱双向工件接力与网络受限爬取调度 REST API：提供共享工件注册 `/agents/cloud-edge-relay/artifacts/register`、CAS 乐观锁增量追加 `/artifacts/append`、工件元数据与聚合全文查询 `/artifacts/{artifact_id}` 与 `/content`、溯源时间线 `/provenance`、以及本地网络出口 SSRF 防护爬取调度 `/relay/dispatch` 与 `/relay/complete`。 | ✅ |
| `virtual_room_router.py` | 路由 | 跨人类-跨Agent协同虚拟空间与文件系统代码共写引擎 REST API：提供多角色空间管理 `/agents/virtual-room/rooms`、VFS 细粒度行块租约锁 `/locks`、零凭据 Agent 借用授权与受管中继 `/grants`、以及即时 Live 端口预览中继网络 `/relays`。 | ✅ |
| `swarm_offload_router.py` | 路由 | 高并发子智能体集群调度与透明云沙箱算力卸载 REST API：提供 10-15 并发子智能体高吞吐批次派发 `/agents/swarm-offload/dispatch`、批次摘要与工件查询 `/batches/{batch_id}`、宿主机物理资源实时水位 `/watermark`、探针上报 `/watermark/report` 与全局卸载策略更新 `/policy`。 | ✅ |
| `visual_timeline_router.py` | 路由 | 多智能体可视化时间轴与单 Agent 节点精准 Cherry-Pick 撤销 REST API：提供时间轴原子节点记录 `/agents/visual-timeline/nodes`、多维条件过滤查询 `/nodes/query`、单节点详情 `/nodes/{node_id}` 与外科手术式精准 Cherry-Pick 原子撤销 `/nodes/{node_id}/rollback`。 | ✅ |
| `clean_code_pipeline_router.py` | 路由 | Clean-Code 装配流水线与架构依赖关系 Lint 检查 REST API：提供五阶段装配流水线创建 `/agents/clean-code/tasks`、单向步进工件推进与分层架构拦截门 `/tasks/{id}/advance`、流水线状态全景 `/tasks/{id}` 与独立 AST 架构 Lint 端点 `/linter/check`。 | ✅ |
| `fusen_router.py` | 路由 | 多智能体轻量级 Fusen 便签看板与共享状态同步 REST API：提供无中心便签发布 `/agents/fusen/notes`、便签就地解决 `/notes/{id}/resolve`、单便签检索 `/notes/{id}`、多维过滤列表 `/notes`、亚毫秒级阻塞判定 `/blockers` 与过期便签自动清理 `/cleanup-expired`。 | ✅ |
| `vertical_presets_router.py` | 路由 | 五大垂直角色 Persona 预设与单 Bot 隔离沙箱测试 REST API：提供预设目录列表与分类过滤 `/agents/vertical-presets`、单预设详情查询与自定义注册 `/{role_id}`、单 Bot 隔离沙箱测试运行 `/test-sandbox`、Agent 通信链步骤记录 `/traces/record` 与会话链路及死循环诊断查询 `/traces/{session_id}`。 | ✅ |
| `council_router.py` | 路由 | 高阶决策多模型审议委员会与交叉仲裁共识 REST API：提供会话初始化与列表 `/agents/council/sessions`、会话状态与共识结果查询 `/{session_id}`、独立盲审方案提交 `/{session_id}/proposals`、匿名交叉质询 `/{session_id}/critiques`、反驳答辩 `/{critique_id}/rebuttal` 与审议阶段推进及共识触发 `/{session_id}/advance`。 | ✅ |
| `kanban_dispatcher_router.py` | 路由 | 可视化看板多智能体工作流分发与任务卡片交接 REST API：提供五泳道看板状态与卡片列表查询 `/chats/{chat_id}/kanban-dispatcher`、卡片创建 `/cards`、流转与智能体自动认领交接 `/cards/{card_id}/handoff`、阻塞标记与解除 `/cards/{card_id}/block` 以及会话重置 `/reset`。 | ✅ |
| `cli_passthrough_router.py` | 路由 | 外部 CLI 子代理适配桥梁与官方订阅无感穿透调度 REST API：提供外部 CLI 包与 BYOS 订阅探测 `/agents/cli-passthrough/bundles`、委派前如实隐私披露签发与确认 `/disclosures` 及 `/acknowledge`、非交互静默执行 `/execute`、不可篡改审计账本查询 `/audit-log` 与重置 `/reset`。 | ✅ |
| `dag_orchestrator_router.py` | 路由 | DAG 可视化编排、多拓扑校验、Cold Resume 断点恢复与双向驳回 REST API：提供工作流创建 `/chats/{chat_id}/dag-orchestrator/workflows`、状态全景快照 `/{workflow_id}`、拓扑图结构与无环校验 `/validate`、就绪节点多路执行推进 `/advance`、快照落盘导出 `/snapshot`、离线零冗余冷恢复 `/resume` 与下游双向缺陷驳回重做 `/reject-loopback`。 | ✅ |
| `kanban_queue_router.py` | 路由 | 多智能体持久任务看板队列与 12 路大规模并行 Dogfooding 运行器 REST API：提供 5 态流转任务增查 `/chats/{chat_id}/kanban-queue/jobs`、认领/完成/阻塞/解除 `/claim`、`/complete`、`/block`、`/unblock`、心跳上报 `/heartbeat`、协作评论与黑板同步 `/comments`、依赖链接 `/link`、自动 Triage 细化 `/specify`、Fan-out 子任务展开 `/decompose`、热熔断开关 `/circuit-breaker`、4h 僵死心跳回收 `/reclaim-stale`、Swarm 共享黑板查询 `/blackboard`、12 路并行波次调度 `/batch/dispatch`、检查点状态 `/batch/status` 与 HuggingFace JSONL 轨迹导出 `/batch/trajectories`。 | ✅ |
| `diamond_graph_router.py` | 路由 | 钻石拓扑编排器与盲审对抗审计包 REST API：提供 3 阶段钻石管道创建 `/chats/{chat_id}/diamond-graph/pipeline`、假依赖静态修剪 `/prune`、扇出并发派发 `/dispatch`、节点完成与 CoT 物理隔离存储 `/nodes/complete`、Dead-Node Census 哨兵统计 `/census`、丢失分支立即重试 `/retry`、确定性 0-Token 规约 `/reduce`、高阶综合 `/synthesize`、节点清单查询 `/nodes`、对抗盲审与真实锚点判定 `/audit`、以及会话重置 `/reset`。 | ✅ |
| `coauthoring_ledger_router.py` | 路由 | 人机多方围绕单一动态文档协同编辑的状态机账本与冲突仲裁 REST API：提供协作者注册 `/chats/{chat_id}/coauthoring-ledger/collaborators`、文档初始化 `/document/init`、块列表与 Markdown 渲染 `/blocks` 与 `/markdown`、块租约申请与释放 `/leases/acquire` 与 `/leases/release`、原子增量提交 `/deltas`、作者贡献度统计 `/contributions`、语义冲突仲裁 `/arbitrate`、暂存提议列表与接纳 `/proposals` 与 `/proposals/{proposal_id}/accept`、冲突记录 `/conflicts` 以及会话重置 `/reset`。 | ✅ |
| `socket_mesh_router.py` | 路由 | 基于 Unix Socket / 命名管道的极简去中心化同机多 Agent 协同网格 REST API：提供同机对等节点注册与发现 `/agents/socket-mesh/projects/{project}/peers`、原子信封协议消息投递 `/messages/send` 与回复 `/messages/reply`、异步等待响应 `/messages/{msg_id}/await`、实时健康探针与遥测卡检索 `/peers/{target_name}/ping`、网格审计日志 `/audit-logs` 与失活节点清理 `/cleanup`。 | ✅ |
| `bot_forge_router.py` | 路由 | 对话式智能体与团队工厂、确定性创建流水线与建造者权限安全边界 REST API：提供名称唯一性与语义重叠检测 `/agents/bot-forge/sessions/{session_id}/check-overlap`、单 Agent 确定性就绪核验创建 `/create-agent`、全队原子创建与故障整队回滚 `/create-team`、人设姓名清洗克隆 `/clone-agent`、会话花名册列表 `/agents`、单个 Agent 查询与删除 `/agents/{name}`。 | ✅ |
| `external_bundle_router.py` | 路由 | 异构外部 Agent 容器化收编与多路复用调度器 REST API：提供外部子 Agent Bundle 注册与目录列表 `/agents/external-bundles`、单 Bundle 详情查询与删除 `/{bundle_id}`、无锁多路复用批量并发调度派发 `/multiplexer/batch-dispatch` 与沙箱越权与实例生命周期治理。 | ✅ |
| `kanban_orchestrator_router.py` | 路由 | WebUI 多智能体持久化任务看板调度中枢、卡片依赖 DAG 拓扑与工件挂载分发器 REST API：提供项目看板增查 `/agents/kanban-orchestrator/boards`、任务卡片创建与无环依赖检查 `/boards/{id}/cards`、泳道流转与自动解锁级联 `/cards/{id}/transition`、工件挂载 `/artifacts`、人机一体拖拽干预 `/override` 与 Boss Agent 目标自动拆解 `/decompose`。 | ✅ |
| `fleet_router_router.py` | 路由 | 跨机分布式舰队 Profile Rail 全景导航轨、多网关拓扑自愈、离线缓冲与跨机工件中继 REST API：提供多节点网关增查与注销 `/fleet/gateways`、心跳遥测与 DEGRADED 判定 `/heartbeat`、Profile 注册 `/profiles`、宿主拓扑上下文注入 `/profiles/{id}/context`、离线指令排队缓冲 `/buffer` 与自愈排空 `/flush`、以及 SHA-256 跨网关工件中继 `/relay` 与分布式拓扑快照 `/topology`。 | ✅ |
| `graph_triage_router.py` | 路由 | 图工程自适应适用性评估门禁与并发 Token 预算熔断 REST API：提供任务模式准入/拦截启发式评估 `/agents/graph-triage/assess`、扇出前置 Token 与费用预算评估 `/estimate-budget`、会话硬上限与初始并发配置 `/sessions/{session_id}/configure`、实时消费上报与限流状态流转 `/sessions/{session_id}/update-spend`、当前预算水位查询 `/sessions/{session_id}/status`、以及危急预算状态下优雅局部归约触发 `/sessions/{session_id}/early-reduce`。 | ✅ |
| `orthogonal_reviewer_router.py` | 路由 | 正交双视角审查门禁与零偏见盲审子代理 REST API：提供意图一致性单项审查 `/agents/orthogonal-reviewer/review-intent`、全新盲态无偏代码审查 `/review-blind`、正交双重视角一站式综合仲裁审查 `/evaluate`、会话级审查历史查询与状态维护 `/sessions/{session_id}/latest`、以及阻断缺陷一键生成修复指令 `/sessions/{session_id}/auto-fix`。 | ✅ |
| `delegation_transcript_router.py` | 路由 | 子 Agent 实时透明 Live Transcript 与后台委派任务持久化恢复 REST API：提供后台委派任务创建与查询 `/delegation-transcript/tasks`、状态流转与完成结算 `/tasks/{id}/status`、进度检查点与工件保存 `/tasks/{id}/checkpoint`、实时事件派发与分页流查询 `/tasks/{id}/events`、单次命令绑定 Smart Approvals 动态审核 `/approvals/evaluate` 与交互式 /deny 拒绝反馈 `/approvals/{id}/resolve`、单次消费防篡改鉴权 `/approvals/{id}/consume`、进程重启孤儿任务自愈恢复 `/ledger/recover`、以及 MoA 角色细粒度推理强度与 Token 预算分配 `/reasoning/allocate`。 | ✅ |







