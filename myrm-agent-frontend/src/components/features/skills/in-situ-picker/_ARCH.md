# Item 120: InSituWorkflowSkillPickerAndQuickMountDrawerSuite 架构设计

## 1. 核心定位与业务价值
彻底破除用户在处理专业任务（如数据分析、长文档提取、复杂爬虫）时，必须中断当前对话、跳转到全局设置页面搜索安装技能的糟糕割裂体验。通过在会话内提供原地嵌入式快速技能探索器与一键挂载抽屉，结合动作空间噪声计（NoiseGauge）与双重安全扫描，实现 2 秒内无缝扩展智能体能力。

## 2. 核心架构与模块划分
- `inSituSkillPickerTypes.ts`: 技能模型、动作空间拥挤度评级（optimal / moderate / crowded / overloaded）、安全扫描状态机、postMessage 跨窗口交互协议。
- `skillNoiseEstimator.ts`: 纯算法动作空间噪声计算引擎，动态评估工具召回开销与 Token 预算负载，支持悬停技能的增量预估（Delta Noise Estimation）。
- `useInSituSkillPickerStore.ts`: Zustand 集中式状态管理。负责可用技能名册、快速检索与领域标签过滤、实时挂载/卸载、Sash 拖拽高度持久化、postMessage 白名单安全过滤。
- `InSituSkillCard.tsx`: 模块化卡片组件，展示技能简述、作者、星标、工具量、预估 Token 开销、Myrm 原生安全审计徽标与一键装配按钮。
- `InSituWorkflowSkillPickerDrawer.tsx`: 抽屉容器组件，集成顶部 Sash 拖拽手柄、NoiseGauge 动态噪声看板、搜索过滤栏与技能流式网格。
- `index.ts`: 统一聚合导出出口。

## 3. 安全协议与上下文治理
- 跨窗口/iframe 消息遵循 `postMessage` 协议，严格校验 `origin` 白名单（杜绝未知源伪造指令注入恶意工具）；
- 结合 Myrm 独有的安全沙箱扫描状态（`safetyScanStatus`）校验，从源头杜绝高危提权或脚本注入风险。
