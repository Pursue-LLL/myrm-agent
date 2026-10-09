# settings/sections/system/

## 架构概述

系统 Tab：WebUI 配置、访问地址、浏览器池、内存监控、系统诊断、安全策略、用量统计、Trace 可视化等。`SystemSection` 为本地/WebUI 模式入口，`SystemCenterSection` 为 Tab 容器。

## 文件清单

### 入口与容器

| 文件                                  | 职责                                                                                                    |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `SystemSection.tsx`                   | WebUI 开关、端口、系统诊断等主面板（共享 Toggle；帷幕/锁屏卡片绑定暂存值）                                                                    |
| `SystemConfigCard.tsx`                | 系统配置卡（托盘/开机启动/快捷键/空闲回收/WebUI 端口与密码 + 保存与重启）：纯呈现，状态与持久化由 SystemSection 持有 |
| `ShortcutRecorder.tsx`                | 全局快捷键录制输入框（聚焦录制 / Esc 取消 / Backspace 清空） |
| `AppshotExcludedAppsEditor.tsx`       | Appshot 隐私黑名单编辑器 |
| `SystemCenterSection.tsx`             | 系统 Tab 容器                                                                                           |
| `AboutSection.tsx`                    | 关于/版本信息                                                                                           |
| `StackUpdatePanel.tsx`                | 全栈更新与版本控制中心（Tauri OTA / WebUI / Git behind / 分组更新日志 / 勿扰窗口 / 自检Doctor并发防重） |
| `__tests__/StackUpdatePanel.test.tsx` | 全栈更新面板单测（OTA三态、Changelog折叠、推迟版本、自检Doctor与Pending禁用、勿扰时段）                 |
| `ImportExportSection.tsx`             | 配置导入导出                                                                                            |

### 存储管理

| 文件                                      | 职责                                                                                                                   |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `StorageCard.tsx`                         | 存储位置与会话数据库智能优化（当前路径、磁盘三元组用量、预检、FTS/VACUUM/WAL双模式瘦身、迁移＋实时进度条、低空间预警） |
| `__tests__/StorageCard.test.tsx`          | 迁移目录高敏链路回归：先签发敏感操作票据，再执行迁移；目录选择取消不签发票据；拒绝/取消场景错误提示                    |
| `__tests__/StorageCard.optimize.test.tsx` | 数据库存储优化完整流程回归：三元组容量预检、Deep/Light双模式选择、活跃任务拦截门禁与优化成功 Toast 反馈                |

### 网络与访问

| 文件                               | 职责                                                                                                                                                                                                                                                      |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AccessCard.tsx`                   | 访问地址、CF tunnel 启停、Mobile Hub QR、PWA 引导、E2EE 指纹与算法详情                                                                                                                                                                                    |
| `ServerConnectionCard.tsx`         | Tauri Desktop 远程服务器网关：本地/远程模式切换、多档案 roster、URL 输入、连接测试、断开恢复本地 token；切换经 `connection-switch-guard` 健康门（测活拦截+二次点击强制，reload 后复验失败按 roster id 回滚，回滚到本地显式 `switchRemoteFollow(false)` 重启后端；云档案持 OAuth 校验免检；切换占座全局互斥：添加/选择/断开/发现沙箱同一时刻只允许一个切换在飞，占座期间档案行、添加、断开开关、发现按钮统一禁用，当前行显示“切换中”，取消/失败/断开完成时释放）；Rust 侧编排先于 apply（失败 toast 提示且 UI 状态零变化，可安全重试）；切断当前连接前的活跃会话 guard（`useActiveSessionsGuard`：有生成中会话弹 `ActiveSessionsSwitchConfirmDialog` 知情确认，查询失败或 3 s 无应答放行不锁死；添加/选择档案、断开回本地、发起云端登录、发现沙箱五条入口共用）；发现沙箱经 `commitSwitch`（可信）先编排后建 Cloud 档案；reload 由 `app:connections-changed` 事件全局驱动 |
| `ActiveSessionsSwitchConfirmDialog.tsx` | 切断连接前（含发起云端登录前）活跃会话知情确认对话框，文案如实说明切换可能中断当前连接上进行中的轮次（本地 sidecar 优雅停机后强杀；远程连接断开超过宽限期后非长任务被服务端取消）（六语言 locales `activeSessionsDialog`，复用 primitives AlertDialog，indigo 主题）                                                                                                                               |
| `useActiveSessionsGuard.ts` | 切断连接前活跃会话守卫 Hook（`getActiveSessions` 查询，有生成中会话时暂存继续动作并输出确认对话框状态，取消回调复位调用方进行中状态；查询失败或超过 3 s 无应答放行，不卡住切走不可达连接；查询进行中的重复触发被忽略，避免并发跑出多次切换） |
| `useConnectionsRollbackGuard.ts` | 连接切换复验回滚 Hook（reload 后 pending 复验、不可达按 last-good 回滚、本地回滚显式重启后端；导出 `testRemoteHealth` 探测函数供连接守卫域共享）                                                                                  |
| `RemoteFirstRunChooser.tsx`        | 首启三选一（本机/远端/云托管，一次性指引，可关闭）                                                                                                                                                                                                        |
| `ServerConnectionCloudSection.tsx` | 云托管区：CP 登录方式查询、浏览器 OAuth（PKCE S256；无法拉起浏览器或准备失败时提示）、沙箱发现验证 token；登录与发现都先经父级注入的 `guardSwitch` 确认，真正的切换与建档由父级完成                                                                                                                                                                                         |
| `ServerConnectionRoster.tsx`       | 远程档案 roster 纯展示子组件：测试/切换/移除三动作回调（任一切换占座期间所有切换按钮禁用），状态与副作用留在 ServerConnectionCard |
| `TrustBadgeCard.tsx`               | 官方发行信任徽章（Tauri限定）：签名态三态诚实呈现 + 官网/下载/Releases 深链                                                                                                                                                                               |
| `RecoveryGuideCard.tsx`            | 崩溃恢复向导（Tauri限定）：失败事件显现 + About常驻；仅非破坏三动作（重试/诊断/重装深链）                                                                                                                                                                 |
| `WebuiAccessSecurityPanel.tsx`     | WebUI 访问安全配置                                                                                                                                                                                                                                        |

### 通知

| 文件                       | 职责                                                        |
| -------------------------- | ----------------------------------------------------------- |
| `PushNotificationCard.tsx` | Web Push VAPID 订阅（`usePushSubscription` SSOT；非 Tauri） |

### 浏览器管理

| 文件                                        | 职责                                                                                                                                                                                                                                                                                                                                                            |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `BrowserPoolCard.tsx`                       | 本地浏览器池管理                                                                                                                                                                                                                                                                                                                                                |
| `BrowserDoctorCard.tsx`                     | 浏览器栈诊断（`/health/browser/doctor`；可选 launch test）+ 孤儿进程清理（`DELETE /health/browser/orphans?confirm=true`，含沙箱清理与磁盘释放空间格式化回显、失败明细、清理前后状态清理、弹窗失败即关）；错误响应 JSON 解析（FastAPI `{"detail": ...}` 字符串/校验数组首项、server 全局兜底 `{success, message}` → 可读文案，非 JSON 原样显示，空值兜底本地化） |
| `CloudBrowserCard.tsx`                      | 云端浏览器配置                                                                                                                                                                                                                                                                                                                                                  |
| `BrowserProxyCard.tsx`                      | 浏览器代理配置                                                                                                                                                                                                                                                                                                                                                  |
| `DomainSkillsCard.tsx`                      | 域技能管理（列表/删除/内置标识）                                                                                                                                                                                                                                                                                                                                |
| `SavedSessionsCard.tsx`                     | 已保存浏览器会话管理（加密登录态/删除/过期清理）                                                                                                                                                                                                                                                                                                                |
| `LockedUseCard.tsx`                         | 锁定使用模式（Computer Use 锁屏管理）                                                                                                                                                                                                                                                                                                                           |
| `PrivacyCurtainCard.tsx`                    | 工位防窥帷幕（开关 + active 回显（订阅 `curtain:state-changed` 实时刷新）+ 手动拉起/收起；Tauri 限定，`privacy_curtain_active` / `show_privacy_curtain` / `hide_privacy_curtain`）                                                                                                                                                                                       
| `__tests__/LockedUseCard.test.tsx`          | 锁屏可用卡片单测（web 不渲染 / switch 语义与 onToggle 下一值 / 平台不支持时禁用）3 cases |
| `__tests__/SystemSection.test.tsx`          | 系统面板整页测试：帷幕/锁屏开关绑定暂存值（点击即翻转、置脏、经整页保存持久化）4 cases |
| `__tests__/PrivacyCurtainCard.test.tsx`     | 帷幕卡片单测（web 不渲染 / 状态回显 / 拉起收起 IPC / toast 回馈 / 错误路径 / switch 语义与 toggle 透传 / 回显失败韧性）8 cases                                                                                                                                                                                                                                                |
| `__tests__/ShortcutRecorder.test.tsx`       | 快捷键录制器单测（聚焦录制提示 / 占位文案 / 组合键归一 / 纯修饰键忽略 / Backspace 清空与 Esc 取消）5 cases |
| `DesktopPermissionsCard.tsx`                | 桌面自动化就绪检测：首屏 grant-only 四态（verified=`capture_ready` / unverified / capture_failed / missing）+ 刷新 `?probe_capture=true` + 功能捕获行 + 始终信任应用（`GET/DELETE /webui/desktop/trust/apps`）                                                                                                                                                  |
| `DesktopPermissionsRows.tsx`                | 桌面权限卡片子组件视图行（`PermissionRow` / `CaptureProbeRow` / `ScreenLockRow` / `DeeplinkItem`）                                                                                                                                                                                                                                                              |
| `__tests__/DesktopPermissionsCard.test.tsx` | vitest：首屏未验证 / capture_failed / Recheck 达 allReady / deeplink / API fail / trusted revoke / trust load error                                                                                                                                                                                                                                             |

### 安全策略

| 文件                                             | 职责                                                                                                                                                                                                                                                                                               |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SecurityPolicySection.tsx`                      | 安全策略主面板（能力面矩阵、自定义规则列表、命令/域名网络策略、超时配置、Org MAP 只读锁定）                                                                                                                                                                                                        |
| `CapabilitySurfaceMatrixGrid.tsx`                | 能力面三态权限矩阵网格（Always/Ask/Deny 卡片组与 Guarded/Balanced/Autonomous 预设切换）                                                                                                                                                                                                            |
| `CustomRulesListEditor.tsx`                      | 自定义权限规则列表编辑器（添加/删除/修改规则，具体工具与通道粒度）                                                                                                                                                                                                                                 |
| `SmartIntentGuardEditor.tsx`                     | 智能意图防护与提示注入拦截开关面板                                                                                                                                                                                                                                                                 |
| `useSecurityPolicy.ts`                           | 安全策略聚合状态 hook（整合能力面规则、网络命令、超时与 ManagedApprovalPolicy 状态）                                                                                                                                                                                                               |
| `useCapabilityRulesPolicy.ts`                    | 能力面矩阵与细粒度规则双向状态同步 hook（处理单通道切换、预设一键应用与持久化）                                                                                                                                                                                                                    |
| `useNetworkCommandPolicy.ts`                     | 网络域名白名单、黑名单与命令禁止模式状态管理 hook                                                                                                                                                                                                                                                  |
| `securityPolicyUtils.ts`                         | 能力面枚举、预设矩阵配置、双向转换与规则扁平化工具函数                                                                                                                                                                                                                                             |
| `securityProfileUtils.ts`                        | 安全 Profile 模板常量与标签映射工具                                                                                                                                                                                                                                                                |
| `__tests__/CapabilitySurfaceMatrixGrid.test.tsx` | 能力面矩阵组件单测（网格渲染、三态按钮切换、预设批量更新）                                                                                                                                                                                                                                         |
| `SecurityPrivacyPanel.tsx`                       | PII 隐私保护面板（含 Privacy Routing，`id=security-privacy-routing` 锚点供 DataFlow 深链）                                                                                                                                                                                                         |
| `DataFlowDisclosurePanel.tsx`                    | 数据流向披露 SSOT：本地域 / deploy-aware 控制平面 / LLM+MCP+OAuth 集成+Agent Connector+Tauri Channel 实时 egress（含 channel SSE 事件刷新）/ Provider training policy / 跨境路由摘要 / Your Rights 合规导出                                                                                        |
| `DataFlowYourRightsStrip.tsx`                    | DataFlow 内「您的数据权利」：client-side compliance JSON 导出（routing API key 脱敏）+ Memory 设置深链                                                                                                                                                                                             |
| `providerDataUsageCatalog.ts`                    | 内置 Provider 数据使用/训练政策静态 catalog（honest doc 外链）                                                                                                                                                                                                                                     |
| `__tests__/DataFlowDisclosurePanel.test.tsx`     | DataFlow 面板单测（deploy / oauth / connectors / Tauri channels / channel SSE 双事件 / cross-border 负向 / API 降级 / 渐进加载 / rights）14 cases                                                                                                                                                  |
| `__tests__/DataFlowYourRightsStrip.test.tsx`     | 合规导出脱敏·snapshot helpers·导出点击成功/失败组件测 9 cases                                                                                                                                                                                                                                      |
| `__tests__/providerDataUsageCatalog.test.ts`     | Provider catalog 单测 3 cases                                                                                                                                                                                                                                                                      |
| `SecurityProfileSelector.tsx`                    | 安全配置模板选择器                                                                                                                                                                                                                                                                                 |
| `NLPolicyGenerator.tsx`                          | AI 自然语言策略生成器                                                                                                                                                                                                                                                                              |
| `AllowlistSection.tsx`                           | Allow Always 持久记录管理（/security/allowlist；permission/tool/exact/pattern 粒度）                                                                                                                                                                                                               |
| `DomainAllowlistEditor.tsx`                      | 域名白名单编辑器                                                                                                                                                                                                                                                                                   |
| `DomainBlocklistEditor.tsx`                      | URL 域名 blocklist 编辑器（Settings 全局策略）                                                                                                                                                                                                                                                     |
| `CommandDenylistEditor.tsx`                      | 命令禁止列表编辑器（fnmatch glob 模式，YOLO 不可绕过）                                                                                                                                                                                                                                             |
| `__tests__/useSecurityPolicy.test.ts`            | useSecurityPolicy hook 单测（command denylist toast 反馈一致性）                                                                                                                                                                                                                                   |
| `PathPolicyEditor.tsx`                           | 路径策略编辑器                                                                                                                                                                                                                                                                                     |
| `RiskRulesSection.tsx`                           | 风控规则配置                                                                                                                                                                                                                                                                                       |
| `RiskRulesHitsPanel.tsx`                         | 风控规则命中记录                                                                                                                                                                                                                                                                                   |
| `RiskRulesTestPanel.tsx`                         | 风控规则测试                                                                                                                                                                                                                                                                                       |
| `risk-rules-types.ts`                            | 风控规则类型定义                                                                                                                                                                                                                                                                                   |
| `ShareLinksSection.tsx`                          | 分享链接管理（`GET/DELETE /api/v1/files/artifacts/shares[/{id}]`：活跃链接表格 + 一键撤销 + 空/加载/错误态 + 刷新；复制/打开优先服务端 `share_url`，无 ingress 时按后端基址/当前 origin 组装；密码分享（share_path 有值）同样渲染复制/打开，无 share_path 的历史密码分享降级为「密码保护中」提示） |

### 用量与成本

| 文件                             | 职责                                                                                                                                   |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `UsageStatisticsSection.tsx`     | 用量统计主面板（时间范围/多维度）；含 Wiki 证据治理卡片（deep verification/requery/dwell/dropped telemetry/negative outcome rate）     |
| `UsageStatisticsCharts.tsx`      | 用量图表 barrel 导出                                                                                                                   |
| `UsageStatCard.tsx`              | 统计卡片                                                                                                                               |
| `UsageCacheBreakTimeline.tsx`    | 缓存击穿时间线                                                                                                                         |
| `UsageDailyChart.tsx`            | 日趋势柱状图 + 缓存命中率折线                                                                                                          |
| `UsageSessionTable.tsx`          | Top 会话表格                                                                                                                           |
| `UsageDistributionCharts.tsx`    | 周/日/小时活动分布图                                                                                                                   |
| `UsagePrivacyRoutePanel.tsx`     | 隐私路由 local/cloud 占比                                                                                                              |
| `UsageModelBreakdown.tsx`        | 模型用量明细                                                                                                                           |
| `AgentUsageCard.tsx`             | Agent 用量卡片                                                                                                                         |
| `BudgetPolicySection.tsx`        | 预算策略与四级渐进式柔性限额风控面板（四级阶梯风控：可视化预警、柔性自确认卡、无损模型自动降级、冻结暂停审批；Fleet Quota 跨维度看板） |
| `ChannelBudgetSection.tsx`       | 渠道预算管理                                                                                                                           |
| `AgentCommerceBudgetSection.tsx` | 智能体受控微预算自主支付与商户白名单消费保险箱面板（单笔/日限额微支付、商户域名白名单、一键紧急熔断与防篡改账本审计）                  |
| `MemoryGuardianCard.tsx`         | 记忆守护者卡片（safe/force 触发、策略配置、晨间摘要夜间窗口聚合）                                                                      |
| `RoutingAnalyticsPanel.tsx`      | 路由分析面板（模型路由/成本格式化）                                                                                                    |

### Trace 可视化与调试

| 文件                                   | 职责                                                                                                                                                                                                                                                                                                      |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ExecutionTraceTimeline.tsx`           | 执行 Trace 时间轴（LLM/Tool 调用链、Replay 入口）；`showEvalCase` prop 控制「保存为评测用例」按钮（kanban 任务无 Chat 记录，RunsHub/看板 Drawer 复用传 `false`）；`pollMs` prop 在任务运行中轮询刷新 trace（展开时实时看到执行过程）；ToolCallItem 渲染 `security_labels`（tainted/deny 徽标 + 展开明细） |
| `SessionAnalyticsDialog.tsx`           | 会话分析对话框（嵌入 ExecutionTraceTimeline + 上下文健康）                                                                                                                                                                                                                                                |
| `SessionContextHealthPanel.tsx`        | 会话上下文健康面板（压缩/裁剪/缓存命中）                                                                                                                                                                                                                                                                  |
| `SessionContextHealthPanelRestore.tsx` | 上下文健康恢复面板                                                                                                                                                                                                                                                                                        |
| `SystemHealthPanel.tsx`                | 系统健康面板（Context Bundle 迁移/诊断）                                                                                                                                                                                                                                                                  |

### 开发者工具

| 文件                              | 职责           |
| --------------------------------- | -------------- |
| `DeveloperSection.tsx`            | 开发者选项入口 |
| `DeveloperCenterSection.tsx`      | 开发者中心     |
| `DatasetExportCard.tsx`           | 数据集导出     |
| `ExperimentalFeaturesSection.tsx` | 实验性功能开关 |

### 功能扩展

| 文件                         | 职责                                                                                                                                                        |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `HeartbeatSection.tsx`       | 心跳巡检配置（含 Agent 绑定 + 模型继承显示）                                                                                                                |
| `CompanionSection.tsx`       | 伴侣模式配置                                                                                                                                                |
| `CronSection.tsx`            | 定时任务管理；点进详情前 `getCronJob` 拉 fresh binding enrich                                                                                               |
| `KanbanSection.tsx`          | 看板任务视图（支持 project scope 列表/创建，`kanban_last_board_id` 按项目持久化；深链 `board_id`/`status` 无视 project filter 全量拉取 board 直达目标任务） |
| `MediaGenerationSection.tsx` | 媒体生成配置                                                                                                                                                |
| `TimezoneSelector.tsx`       | 时区选择器                                                                                                                                                  |

## 连通性 UX

- **LAN 优先**：内网 URL 默认展示。
- **Public Ingress**：本地模式始终展示公网地址输入；用户自选穿透工具后粘贴（文档 `getDocsUrl('/guides/tunnel')`）。
- **Mobile Hub**：tunnel 运行后签发 Hub deep link QR；手机打开 `/mobile` 列表，点会话 mint scoped control token 进入 StatusBoard。
- **条件引导**：`ingress-requirement` 的 `required` 控制引导文案（必须 vs 可选），不影响 Ingress 输入区可见性。
- 判定逻辑：Server `ingress_requirement.py` + 前端 `useIngressRequirement` 单 API。

## 依赖

- `@/hooks/billing/useIngressRequirement`
- `@/hooks/settings/useSystemConfig`
- `@/services/system`
- `@/services/statistics`
- `@/services/budget`
- `@/lib/deploy-mode::getDocsUrl`
- `@/lib/deploy-mode::getRemoteGatewayConfig` / `setRemoteGatewayConfig` / `isTauriRuntime`（ServerConnectionCard）
- `@/lib/remote-follow-switch::switchRemoteFollow`（ServerConnectionCard / local-backend-unavailable-banner：连接切换后端生命周期编排入口）
- `@/services/agent::getActiveSessions`（useActiveSessionsGuard 切断连接前活跃会话查询）
- `@/lib/remote-profiles::ensureCloudProfile`（ServerConnectionCard 发现沙箱切换成功后建立并激活 Cloud 档案）
- `@/lib/desktop-oauth::beginDesktopOAuth`（ServerConnectionCloudSection 发起 state + PKCE 登录）
- `@/lib/connection-switch-guard::setLastGood` / `getLastGood` / `setPendingSwitch` / `getPendingSwitch` / `isPendingFresh`（ServerConnectionCard 切换守卫存储）
