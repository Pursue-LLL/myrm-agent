# WideScreenErgonomicCockpitAndInlineGaitHUDSuite 架构说明与设计决策

## 1. 业务目标与人机工效学痛点
彻底根治大屏与带鱼屏（1920x1080 / 2560x1440 及以上）下信息过度碎片化、用户视线在左上角模型徽章、右上角产物与底部输入框进度条之间三角疲于奔命的严重工效学缺陷。

## 2. 核心架构设计与四大支柱
1. **视线向心聚合（Foveal Centric Layout）**：
   - 将当前沟通智能体身份、模型徽章与任务实时步态紧密锚定在中轴会话流，使焦点保持在视觉黄斑区（Foveal Vision）。
2. **输入框进度解耦与响应顶置步态条（Decoupled In-Bubble Gait Progress）**：
   - 步态 HUD (`InBubbleGaitHUD`) 顶置于最新消息气泡上方，`isDecoupledFromInput: true`，输入框不再被执行进度劫持。
3. **会话流内联自适应实体头像与动态波形（Inline Persona Avatar & State Waveform）**：
   - `InlinePersonaAvatar` 提供思考中（thinking）、外部工具调度（tool_executing）、流式输出（streaming）及完成（completed）的高性能轻量动态波形呈现。
4. **超宽屏自适应三栏同屏联动与向心折叠（Wide-Screen 3-Column Ergonomic Mode）**：
   - 布局由左侧协同拓扑 + 中轴向心对话流 + 右侧工件看板组成，支持一键“向心聚焦”（折叠双翼）或平滑展开。

## 3. 质量指标与红线守护
- 单文件行数受控在 200 行以内（远低于 400 行硬顶）；
- 零 `any`，全面采用 TypeScript 静态强类型；
- 零原生 emoji，统一采用 Lucide 矢量图标；
- 所有 `if` 逻辑采用完整块级大括号包裹。
