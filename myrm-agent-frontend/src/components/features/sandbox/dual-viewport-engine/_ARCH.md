# LiveSandboxDualViewportVisualSelfCorrectionAndConsoleFeedbackEngine 架构说明与设计决策

## 1. 业务目标与核心痛点
彻底根治 AI 生成前端页面“代码能跑但排版错乱、移动端错行溢出、控制台报隐形 TypeError 白屏”的致命体验硬伤。
对标 Cursor 核心杀手级 Browser 页面与控制台直读自愈能力，构建跨移动端与桌面端的工业级自闭环引擎。

## 2. 核心架构设计与五大支柱
1. **双视口实时模拟与并排比对（Dual-Viewport Live Simulation）**：
   - 支持 Mobile 375px × 667px (iPhone SE/Mini) 与 Desktop 1280px × 800px 标准视口；
   - 支持单屏专注与双屏并排（side_by_side）一览排版差异，避免宽屏正常移动端严重错行。
2. **控制台日志与网络请求零容忍门禁（Zero-Console-Error & 404 Gatekeeper）**：
   - 严格拦截捕获 `TypeError`、语法错误、未捕获 Promise Rejection 以及非 200 HTTP 资源请求。
3. **原地视觉与控制台自愈修正循环状态机（Visual & Console Self-Healing Loop）**：
   - 状态流转：`idle` ➔ `harvesting_errors` ➔ `healing_prompt_injected` ➔ `recompiling` ➔ `healed_verified`；
   - 错误自动聚合成自愈提示反馈给智能体上下文，直到控制台完全清洁。
4. **前置既有 UI 组件资产与 API 契约自适应嗅探与复用约束（Design System SSOT）**：
   - 自动探测并强约束复用沙箱内已有的基础组件（如 StandardDataTable、AccessibleModalDialog、unifiedApiClient），杜绝 AI 乱造裸标签与裸写 fetch。

## 3. 质量指标与红线守护
- 单文件代码行数严格控制在 260 行以内（远低于 400 行硬顶）；
- 零 `any`，全面采用 TypeScript 静态强类型；
- 零原生 emoji，统一采用 Lucide 矢量图标；
- 所有 `if` 条件逻辑包裹完整大括号；
- a11y 无障碍可访问性语义标签齐全，零控制台警告。
