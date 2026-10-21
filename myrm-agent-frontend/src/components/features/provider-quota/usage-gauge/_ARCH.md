# Provider Quota & Telemetry Gauge Architecture (`provider-quota/usage-gauge`)

## 1. 架构定位与业务痛点
针对用户（尤其是购买 Nous Portal 或第三方 API 订阅用户）对于用量和剩余百分比无法感知的深层黑盒焦虑（@sahaptanrikulu: *"How can I see my use ? I want to know my usage and percentages."*），以及客户端充当单纯代理缺少配额遥测与长任务突发欠费崩溃的问题，本模块提供生产级实时配额遥测、常驻仪表盘、断流自愈降级与全景 Token 经济学大盘。

## 2. 模块拓扑与职责划分
- **`providerQuotaTypes.ts`**：强类型契约，定义多提供商快照、健康度等级（healthy/warning/critical/exhausted）、时序数据点与故障转移恢复动作；
- **`quotaTelemetryParser.ts`**：纯函数遥测解析器，支持从 OpenAI、Anthropic、Nous Portal 等上游网络响应头中自动提取剩余 Token、USD 余额与限流重置时间，并计算健康等级与可用天数；
- **`useProviderQuotaStore.ts`**：Zustand 全局状态总线，管理多渠道实时遥测、耗尽熔断预警控制、一键自愈故障转移与模型消耗分布；
- **`ProviderQuotaGaugeBadge.tsx`**：常驻顶部导航与状态栏的微型仪表徽章，支持颜色梯度指示、健康呼吸灯与快速换源下拉菜单；
- **`QuotaExhaustionWarningBanner.tsx`**：柔性预警卡片，当额度低于阈值时弹出，支持保护会话现场与一键热切换备用模型；
- **`ProviderQuotaAnalyticsModal.tsx`**：全景 Token 经济学时序大盘与账单弹窗，展示模型分布占比条、智能体角色开销、7日走势柱状图与 CSV 账单导出。

## 3. 极不友好 Code Review 12 项清单遵循度
1. **零 Any**：全链路采用强类型定义；
2. **零原生 Emoji**：统一采用 Lucide 矢量图标；
3. **前端所有 If 显式带大括号**：绝无单行省略括号语法；
4. **代码行数严格控制**：单文件全部受控在 300 行以内；
5. **无障碍 a11y 标准**：满足 aria-label、键盘交互与焦点事件处理。
