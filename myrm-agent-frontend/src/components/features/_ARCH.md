# features/

## 架构概述

按产品域划分的客户端 UI：对话、设置、记忆、看板、技能等。页面 (`src/app/*`) 保持薄壳，主要逻辑在本目录子模块中。

## 子模块（目录）

| 目录                                          | 职责                                                                 | 文档                                                                              |
| --------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `app-shell/`                                  | 启动屏、认证/PWA 初始化器、全局对话框                                | [_ARCH.md](app-shell/_ARCH.md)                                                    |
| `chat-window/`                                | 主对话窗口、审批、Agent 配置、目标 DAG                               | [_ARCH.md](chat-window/_ARCH.md)                                                  |
| `message-box/`                                | 消息渲染与进度                                                       | [_ARCH.md](message-box/_ARCH.md)                                                  |
| `sidebar/`                                    | 会话侧栏                                                             | [_ARCH.md](sidebar/_ARCH.md)                                                      |
| `settings/`                                   | 设置页各 Section（含 Settings→通信→渠道 Provider 配置卡）            | [_ARCH.md](settings/_ARCH.md)                                                     |
| `memory/`                                     | 记忆中心                                                             | [_ARCH.md](memory/_ARCH.md)                                                       |
| `instance-archive/`                           | 整实例备份与恢复（导出、定时自动备份、导入向导、首次启动入口、撤销、重启提示、全局结果通知）                   | [_ARCH.md](instance-archive/_ARCH.md)                                             |
| `skills/`                                     | 技能管理、进化审核 Dashboard                                         | [_ARCH.md](skills/_ARCH.md)                                                       |
| `plugins/`                                    | Agent Plugins 1.0.0 导入向导 + 专家导出                              | [_ARCH.md](plugins/_ARCH.md)                                                      |
| `redaction/`                                  | 导出前脱敏复核（技能导出与专家导出共用）                             | [_ARCH.md](redaction/_ARCH.md)                                                    |
| `kanban/`                                     | 看板                                                                 | [_ARCH.md](kanban/_ARCH.md)                                                       |
| `projects/`                                   | 项目域仪表盘（Kanban/Cron/Artifacts 入口聚合）                       | [_ARCH.md](projects/_ARCH.md)                                                     |
| `project-workspace/`                          | Project 级同步目录绑定 UI（Mount Wizard）                            | [_ARCH.md](project-workspace/_ARCH.md)                                            |
| `health/`                                     | System Doctor                                                        | [_ARCH.md](health/_ARCH.md)                                                       |
| `onboarding/`                                 | 首次启动向导（迁移 + 本地能力 + Cookbook）                           | [_ARCH.md](onboarding/_ARCH.md)                                                   |
| `workspace/`                                  | 工作区与文件树                                                       | [_ARCH.md](workspace/_ARCH.md)                                                    |
| `cron/`                                       | 定时任务 UI                                                          | [_ARCH.md](cron/_ARCH.md)                                                         |
| `artifacts/`                                  | 工件与部署                                                           | [_ARCH.md](artifacts/_ARCH.md)                                                    |
| `companion/`                                  | 桌宠伴侣                                                             | [_ARCH.md](companion/_ARCH.md)                                                    |
| `copilot/`                                    | Lean Co-Pilot：Run Observer + Session Advisor（旁路只读问答）        | [_ARCH.md](copilot/_ARCH.md)                                                      |
| `e2ee/`                                       | E2EE 安全状态 badge + Popover 面板                                   | [_ARCH.md](e2ee/_ARCH.md)                                                         |
| `mobile/`                                     | Mobile Session Hub + 远程 HITL StatusBoard（`/mobile` 路由）         | [_ARCH.md](mobile/_ARCH.md)                                                       |
| `browser-inspector/`                          | 浏览器检查器                                                         | [_ARCH.md](browser-inspector/_ARCH.md)                                            |
| `desktop-inspector/`                          | 桌面检查器                                                           | [_ARCH.md](desktop-inspector/_ARCH.md)                                            |
| `image-editor/`                               | 图片标注编辑器（Canvas API）                                         | [_ARCH.md](image-editor/_ARCH.md)                                                 |
| `workspace-browser/`                          | 工作区内嵌文件浏览器与预览                                           | [_ARCH.md](workspace-browser/_ARCH.md)                                            |
| `background-tasks/`                           | 后台任务面板                                                         | [_ARCH.md](background-tasks/_ARCH.md)                                             |
| `browser-recording/`                          | 浏览器录制回放                                                       | [_ARCH.md](browser-recording/_ARCH.md)                                            |
| `files/`                                      | 文件展示层共享组件（文件类型图标）                                   | —                                                                                 |
| `checkpoint/`                                 | 会话检查点 UI                                                        | [_ARCH.md](checkpoint/_ARCH.md)                                                   |
| `eval-lab/`                                   | 评测实验室                                                           | [_ARCH.md](eval-lab/_ARCH.md)                                                     |
| `growth/`                                     | Growth 草稿与推广                                                    | [_ARCH.md](growth/_ARCH.md)                                                       |
| `icons/`                                      | 功能域专用图标（非 Lucide 通用集）                                   | [_ARCH.md](icons/_ARCH.md)                                                        |
| `image-gen/`                                  | 图片生成 UI                                                          | [_ARCH.md](image-gen/_ARCH.md)                                                    |
| `markdown-render-tools/`                      | Markdown 渲染扩展（Mermaid、代码块等）                               | [_ARCH.md](markdown-render-tools/_ARCH.md)                                        |
| `message-actions/` / `message-input-actions/` | 消息操作与输入区动作                                                 | [_ARCH.md](message-actions/_ARCH.md) · [_ARCH.md](message-input-actions/_ARCH.md) |
| `notifications/`                              | 通知中心                                                             | [_ARCH.md](notifications/_ARCH.md)                                                |
| `task-card/`                                  | 任务卡片组件                                                         | [_ARCH.md](task-card/_ARCH.md)                                                    |
| `theme/`                                      | Theme Engine v2（预设、壁纸、Compiler runtime）                      | [_ARCH.md](theme/_ARCH.md)                                                        |
| `theme-studio/`                               | Theme Studio：四步向导创建 ThemeProfileRecipe + 预览/导出 .myrmtheme | [_ARCH.md](theme-studio/_ARCH.md)                                                 |
| `voice/`                                      | 语音输入/会话 UI                                                     | [_ARCH.md](voice/_ARCH.md)                                                        |
| `file-preview/`                               | 通用文件预览                                                         | [_ARCH.md](file-preview/_ARCH.md)                                                 |
| `research/`                                   | Research 三栏研究工作台（资料池 + Chat + 工件输出）                  | [_ARCH.md](research/_ARCH.md)                                                     |
| `runs/`                                       | Unified Runs Hub 聚合运行历史                                        | [_ARCH.md](runs/_ARCH.md)                                                         |
| `loadout/`                                    | Agent Loadout 摘要 + Team Assets Hub（组合现有 API/面板）            | [_ARCH.md](loadout/_ARCH.md)                                                      |
| `embeds/`                                     | 外链 URL 富媒体嵌入（provider 匹配 + consent + iframe）              | [_ARCH.md](embeds/_ARCH.md)                                                       |
| `presentation/`                               | 演示文稿（PPT）生成弹窗、幻灯片渲染与预览下载                        | [_ARCH.md](presentation/_ARCH.md)                                |
| `task-inspector/`                             | 任务执行实时透视镜与技能调用时序可视化看板（步骤树、瀑布流、毫秒级耗时、插嘴打断） | [_ARCH.md](task-inspector/_ARCH.md)                                               |
| `reconnect-protocol/`                         | 基于单次原子状态快照与零事件重放 Live SSE 订阅的前后端无缝重连协议（极简状态胶囊、原子快照对齐与纯 Live 增量流） | [_ARCH.md](reconnect-protocol/_ARCH.md)                                           |
| `commands/`                                   | 情境感知型渐进式能力即时推荐、交互式快捷指令全景面板（“鼠标垫视图”）与智能微引导引擎 | [_ARCH.md](commands/_ARCH.md)                                                     |
| `canvas/`                                     | Canvas 画布文件严格沙箱隔离与交互式脚本动态鉴权体系（Strict CSP、iframe sandbox、出网审批门禁） | [_ARCH.md](canvas/_ARCH.md)                                                       |
| `quad-graph/`                                 | 四图分层动态拓扑视界与可观测图控制台（Task/Workflow/Team/Communication 四重视角切换、节点光晕点亮与实时 Steer 驾驶舱） | [_ARCH.md](quad-graph/_ARCH.md)                                                   |
| `roi-dashboard/`                              | 智能体可量化 ROI 生产力大盘与已节省时间价值看板（显性化工时大盘、投入产出比、任务分类贡献与高收益预置流程） | [_ARCH.md](roi-dashboard/_ARCH.md)                                               |
| `extension-widgets/`                          | 扩展小组件 ANSI 颜色渲染器与微型组件挂载宿主（Nano-Context 上下文占用表、Todo 任务清单） | [_ARCH.md](extension-widgets/_ARCH.md)                                           |
| `model-tester/`                               | 模型配置一键测速与连通性自检器（首字延迟 TTFT、TPS 吞吐量、呼吸状态健康徽标） | [_ARCH.md](model-tester/_ARCH.md)                                                 |
| `runtime/`                                  | 纯函数式多端状态投影中枢、实时运行时控制台与 Attempt 状态变迁透视抽屉（Quad-Surface 视图切换、Attempt 水位线与故障诊断） | [_ARCH.md](runtime/_ARCH.md)                                                     |
| `browser-annotation/`                       | 内置预览浏览器「点选圈批」与 DOM/CSS 元素精准批注系统（选区高亮、编号 Pin、DOM 特征提取、脱敏与子树分组并行修复） | [_ARCH.md](browser-annotation/_ARCH.md)                                           |
| `workspace-cockpit/`                        | 个人数字员工工作区总控驾驶舱（“你不在的时候”离线成果统计、4 泳道任务流、实时 streaming tail 与悬浮会话托盘） | [_ARCH.md](workspace-cockpit/_ARCH.md)                                             |
| `task-action-preview/`                      | 会话建议智能脱敏清洗转 Task（废话剥离、动宾行动项提炼）与高危操作 Typed Action 范围预览模态框及不可篡改操作回执卡 | [_ARCH.md](task-action-preview/_ARCH.md)                                           |
| `specialty-suites-gateway/`                 | 桌面端统一专业套件侧栏工作台与移动端免配置扫码热插拔伴侣网关（专家套件、企业连接器、统一定时中心、Ed25519 扫码配对） | [_ARCH.md](specialty-suites-gateway/_ARCH.md)                                       |
| `activity-feed/` | 组件 `ActivityFeedAggregatorDeck`、`ActivityFeedStreamCard`；状态仓库 `useActivityFeedStore` | [_ARCH.md](activity-feed/_ARCH.md) |
| `approval/` | 组件 `ExecutiveApprovalCard`、`VisualGatekeepingDeck`；状态仓库 `useExecutiveApprovalStore` | [_ARCH.md](approval/_ARCH.md) |
| `arena/` | 组件 `AdoptSynthesizeBar`、`LocalProjectWorkspaceCard`、`MultiModelSplitArenaView`；状态仓库 `useArenaStore` | [_ARCH.md](arena/_ARCH.md) |
| `artifact-sandbox/` | 组件 `FinancialSandplayWidget`、`InteractiveArtifactSandbox`、`NewsletterRichStyler`；状态仓库 `useArtifactSandboxStore` | [_ARCH.md](artifact-sandbox/_ARCH.md) |
| `clarification-questionnaire/` | 组件 `ClarificationQuestionnaireCard`、`V1SpecSummaryModal`；状态仓库 `useClarificationQuestionnaireStore` | [_ARCH.md](clarification-questionnaire/_ARCH.md) |
| `command-center/` | 组件 `CommandCenterHeaderTrigger`、`CommandCenterMaintenanceTab`、`CommandCenterModal`、`CommandCenterSessionsTab` 等 6 个；状态仓库 `useCommandCenterStore` | [_ARCH.md](command-center/_ARCH.md) |
| `companion-plan-hub/` | 组件 `MicroPlanDrawer`、`MiniArtifactBubble`、`ProgressHUD`；状态仓库 `useCompanionPlanHubStore` | [_ARCH.md](companion-plan-hub/_ARCH.md) |
| `data-migration/` | 组件 `DataMigrationSection`、`MigrationReconciliationModal`、`MigrationSilentToast`；状态仓库 `useDataMigrationStore` | [_ARCH.md](data-migration/_ARCH.md) |
| `desktop-pet-pulse/` | 组件 `DataMigrationCenterModal`、`FloatingPetBall`、`PetControlQuickActionDrawer`、`VoiceDirectInputBubble`；状态仓库 `useDesktopPetPulseStore` | [_ARCH.md](desktop-pet-pulse/_ARCH.md) |
| `dockable-workbench/` | 组件 `DockableChangesViewer`、`DockableWorkbenchContainer`、`TriSurfaceTaskIndicator`；状态仓库 `useDockableWorkbenchStore` | [_ARCH.md](dockable-workbench/_ARCH.md) |
| `dual-track-view/` | 组件 `BusinessMessageCard`、`DualTrackModeSwitcher`、`EngineeringTraceDrawer`；状态仓库 `useDualTrackStore` | [_ARCH.md](dual-track-view/_ARCH.md) |
| `element-editor/` | 组件 `ElementInspectorOverlay`、`ElementVisualEditorContainer`、`InPlaceEditPopover`、`VisualVersionRollbackDeck`；状态仓库 `useElementEditorStore` | [_ARCH.md](element-editor/_ARCH.md) |
| `element-patch/` | 组件 `ElementAnnotationPinOverlay`、`StagedAnnotationsDrawer`、`SurgicalPatchCard`；状态仓库 `useElementPatchStore` | [_ARCH.md](element-patch/_ARCH.md) |
| `floating-pet/` | 组件 `CompanionFloatingPet`、`MiniTaskBubble`；状态仓库 `useFloatingPetStore` | [_ARCH.md](floating-pet/_ARCH.md) |
| `insitu-annotation/` | 组件 `InSituBatchCommentRail`、`InSituCanvasContainer`、`InSituCommentPinLayer`、`InSituPropertyInspector`；状态仓库 `useInsituAnnotationStore` | [_ARCH.md](insitu-annotation/_ARCH.md) |
| `local-first/` | 组件 `LocalFirstPrivacySandboxCard`、`WebGPUMetaArtifactViewer`；状态仓库 `useLocalFirstStore` | [_ARCH.md](local-first/_ARCH.md) |
| `mobile-companion/` | 组件 `MobileRemoteSteeringBar`、`MobileTaskCompanionView`、`QrCodePairingModal`；状态仓库 `useMobileCompanionStore` | [_ARCH.md](mobile-companion/_ARCH.md) |
| `on-demand-confirmation/` | 组件 `NineEntryNavigationShell`、`OnDemandDecisionModal`、`OnDemandOptionCard`；状态仓库 `useOnDemandConfirmationStore` | [_ARCH.md](on-demand-confirmation/_ARCH.md) |
| `search-audit/` | 组件 `SearchAuditDrawer`、`SearchAuditEvidenceBadge`；状态仓库 `useSearchAuditStore` | [_ARCH.md](search-audit/_ARCH.md) |
| `side-chat/` | 组件 `SideChatDrawer`、`SideChatTriggerButton`；状态仓库 `useSideChatStore` | [_ARCH.md](side-chat/_ARCH.md) |
| `side-track/` | 组件 `SideTrackExplainerDrawer`、`SideTrackForkTrigger`；状态仓库 `useSideTrackStore` | [_ARCH.md](side-track/_ARCH.md) |
| `skeuomorphic-app/` | 组件 `ClassicIpodTaskCarouselPlayer`、`PolaroidArtifactAlbumDeck`、`SkeuomorphicWorkbenchWidget`；状态仓库 `useSkeuomorphicAppStore` | [_ARCH.md](skeuomorphic-app/_ARCH.md) |
| `speech-bias/` | 组件 `DevLexiconBiasDrawer`、`VoiceDevConfirmCard`；状态仓库 `useSpeechBiasStore` | [_ARCH.md](speech-bias/_ARCH.md) |
| `swarm-canvas/` | 组件 `ElasticSwarmCanvas`、`SoloFocusLensDrawer`、`SwarmStatusCapsuleBar`；状态仓库 `useSwarmCanvasStore` | [_ARCH.md](swarm-canvas/_ARCH.md) |
| `three-mode-switcher/` | 组件 `ThreeModeCapsuleSwitcher`、`ThreeModeIntentGuidanceToast`、`ThreeModePermissionMatrixDeck`；状态仓库 `useThreeModeStore` | [_ARCH.md](three-mode-switcher/_ARCH.md) |
| `threejs-sandbox/` | 组件 `ThreeJsCanvasViewer`、`ThreeJsConsoleDrawer`、`ThreeJsPerformancePanel`；状态仓库 `useThreeJsSandboxStore` | [_ARCH.md](threejs-sandbox/_ARCH.md) |
| `turn-lineage/` | 组件 `TurnLineageFilterBar`、`TurnOriginBadge`、`TurnProvenanceHoverCard`、`TurnTimelineAuditRail`；状态仓库 `useTurnLineageStore` | [_ARCH.md](turn-lineage/_ARCH.md) |

上表覆盖当前全部 feature 子目录。新增目录须同步本表并添加目录级 `_ARCH.md`。

## 依赖

- `@/components/primitives/*`
- `@/services/*`、`@/store/*`、`@/hooks/*`
