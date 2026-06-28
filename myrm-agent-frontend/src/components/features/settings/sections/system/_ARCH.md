# settings/sections/system/

## 架构概述

系统 Tab：WebUI 配置、访问地址、浏览器池、内存监控、系统诊断、安全策略、用量统计、Trace 可视化等。`SystemSection` 为本地/WebUI 模式入口，`SystemCenterSection` 为 Tab 容器。

## 文件清单

### 入口与容器

| 文件 | 职责 |
|------|------|
| `SystemSection.tsx` | WebUI 开关、端口、系统诊断等主面板 |
| `SystemCenterSection.tsx` | 系统 Tab 容器 |
| `AboutSection.tsx` | 关于/版本信息 |
| `ImportExportSection.tsx` | 配置导入导出 |

### 网络与访问

| 文件 | 职责 |
|------|------|
| `AccessCard.tsx` | 访问地址、CF tunnel 启停、Mobile Hub QR、PWA 引导 |
| `WebuiAccessSecurityPanel.tsx` | WebUI 访问安全配置 |
| `ProxySettingsCard.tsx` | 网络代理设置 |

### 浏览器管理

| 文件 | 职责 |
|------|------|
| `BrowserPoolCard.tsx` | 本地浏览器池管理 |
| `CloudBrowserCard.tsx` | 云端浏览器配置 |
| `BrowserProxyCard.tsx` | 浏览器代理配置 |
| `LockedUseCard.tsx` | 锁定使用模式 |

### 安全策略

| 文件 | 职责 |
|------|------|
| `SecurityPolicySection.tsx` | 安全策略 UI（权限规则/超时/域名白名单/YOLO/Smart Intent Guard） |
| `useSecurityPolicy.ts` | 安全策略状态管理 hook（配置加载/保存/Profile/NL策略生成） |
| `securityPolicyUtils.ts` | 安全策略工具函数（常量/权限扁平化/构建/默认配置） |
| `SecurityPrivacyPanel.tsx` | PII 隐私保护面板 |
| `SecurityProfileSelector.tsx` | 安全配置模板选择器 |
| `NLPolicyGenerator.tsx` | AI 自然语言策略生成器 |
| `AllowlistSection.tsx` | URL/域名白名单管理 |
| `DomainAllowlistEditor.tsx` | 域名白名单编辑器 |
| `PathPolicyEditor.tsx` | 路径策略编辑器 |
| `RiskRulesSection.tsx` | 风控规则配置 |
| `RiskRulesHitsPanel.tsx` | 风控规则命中记录 |
| `RiskRulesTestPanel.tsx` | 风控规则测试 |
| `risk-rules-types.ts` | 风控规则类型定义 |

### 用量与成本

| 文件 | 职责 |
|------|------|
| `UsageStatisticsSection.tsx` | 用量统计主面板（时间范围/多维度） |
| `UsageStatisticsCharts.tsx` | 用量统计图表组件 |
| `UsageModelBreakdown.tsx` | 模型用量明细 |
| `AgentUsageCard.tsx` | Agent 用量卡片 |
| `BudgetPolicySection.tsx` | 预算策略配置 |
| `ChannelBudgetSection.tsx` | 渠道预算管理 |
| `RateLimitMonitor.tsx` | 速率限制监控 |
| `RoutingAnalyticsPanel.tsx` | 路由分析面板（模型路由/成本格式化） |
| `CommitmentPanel.tsx` | 承诺用量管理 |

### Trace 可视化与调试

| 文件 | 职责 |
|------|------|
| `ExecutionTraceTimeline.tsx` | 执行 Trace 时间轴（LLM/Tool 调用链、Replay 入口） |
| `SessionAnalyticsDialog.tsx` | 会话分析对话框（嵌入 ExecutionTraceTimeline + 上下文健康） |
| `SessionContextHealthPanel.tsx` | 会话上下文健康面板（压缩/裁剪/缓存命中） |
| `SessionContextHealthPanelRestore.tsx` | 上下文健康恢复面板 |
| `SystemHealthPanel.tsx` | 系统健康面板（Context Bundle 迁移/诊断） |

### 开发者工具

| 文件 | 职责 |
|------|------|
| `DeveloperSection.tsx` | 开发者选项入口 |
| `DeveloperCenterSection.tsx` | 开发者中心 |
| `DatasetExportCard.tsx` | 数据集导出 |
| `ExperimentalFeaturesSection.tsx` | 实验性功能开关 |

### 功能扩展

| 文件 | 职责 |
|------|------|
| `HeartbeatSection.tsx` | 心跳监控 |
| `CompanionSection.tsx` | 伴侣模式配置 |
| `CronSection.tsx` | 定时任务管理 |
| `DLQSection.tsx` | 死信队列管理 |
| `KanbanSection.tsx` | 看板任务视图 |
| `MediaGenerationSection.tsx` | 媒体生成配置 |
| `TimezoneSelector.tsx` | 时区选择器 |

## 连通性 UX

- **LAN 优先**：内网 URL 默认展示。
- **Public Ingress**：本地模式始终展示公网地址输入；用户自选穿透工具后粘贴（文档 `getDocsUrl('/guides/tunnel')`）。
- **Mobile Hub**：tunnel 运行后签发 Hub deep link QR；手机打开 `/mobile` 列表，点会话 mint scoped control token 进入 StatusBoard。
- **条件引导**：`ingress-requirement` 的 `required` 控制引导文案（必须 vs 可选），不影响 Ingress 输入区可见性。
- 判定逻辑：Server `ingress_requirement.py` + 前端 `useIngressRequirement` 单 API。

## 依赖

- `@/hooks/useIngressRequirement`
- `@/hooks/useSystemConfig`
- `@/services/system`
- `@/services/statistics`
- `@/services/budget`
- `@/lib/deploy-mode::getDocsUrl`
