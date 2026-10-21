# Multi-Pane Flexible Cockpit & Active Bot Pulse Indicator Suite Architecture

## 1. 业务痛点与第一性原理
解决多智能体系统在传统 GUI 中仅有单调左侧列表或标签页，导致用户在多个智能体与定时任务之间频繁切屏；当后台智能体被定时（Cron）或异步唤醒跑任务时，前台毫无视觉反馈；以及缺乏从活跃状态一键穿梭直达任务现场的交互链路。

## 2. 核心架构设计
1. **多栏自由拖拽桌面协同驾驶舱（Resizable Multi-Pane Cockpit）**：
   - `MultiPaneFlexibleCockpit.tsx`
   - 支持二栏 / 三栏 / 四栏模式自由切换与记忆（Bot 团队名册 + 主会话流 + 右侧专属 Cron 监控 + 实时工件反链）。
2. **后台活跃 Bot 动态呼吸与旋转发光指示器（Active Bot Live Pulse & Spin Badge）**：
   - `ActiveBotPulseBadge.tsx`
   - 当智能体处于 `active_cron` / `active_thinking` / `active_tool_exec` 状态时，头像外圈触发柔和发光光晕与旋转状态指示器，一眼看清谁在干活。
3. **Bot 团队名册与一键穿梭直达（Bot Roster & 1-Click Handoff）**：
   - `BotRosterPane.tsx`
   - 展示智能体团队成员列表、向心折叠、高亮活跃任务简述与实时进度条，支持单击【穿梭】直达任务流现场。
4. **专属定时任务检查器（Bot Cron Inspector）**：
   - `BotCronInspectorPane.tsx`
   - 侧边栏常驻选中 Bot 的专属定时任务（Cronjobs）快速创建、执行历史与启停开关。

## 3. 质量指标与红线
- 单文件全部受控在 220 行以内（远低于 400 行）；
- 严禁 `any` 类型；
- 零原生 emoji，全采用 Lucide 矢量图标；
- 严格遵循语义化 HTML（`<aside>`, `<main>`, `<header>`）杜绝 a11y 警告。
