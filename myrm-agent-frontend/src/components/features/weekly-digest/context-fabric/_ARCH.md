# Cross Channel Context Fabric & Autonomous Weekly Digest Synthesizer Suite (`weekly-digest/context-fabric`)

## 1. 架构定位与业务痛点
针对用户在飞书/微信处理短平快任务、在桌面端/Web 端深入分析、在命令行压测，周五写周报时必须人工多头翻找聊天记录与 Git 提交重复整理的严重低效痛点，本模块汲取火山引擎 OpenViking 与豆包工作「换工具、换 Agent、不换上下文」最佳实践，构建跨渠道上下文共享工作足迹池与全自动结构化周报合成微调引擎。

## 2. 模块拓扑与职责划分
- **`weeklyDigestTypes.ts`**：强类型契约定义跨渠道工作足迹 `ChannelFootprintItem`、周报合成摘要 `WeeklyDigestSummary`、风格预设 `DigestStylePreset`（高管审阅级/研发技术向/极简子弹点）与微调指令 `RefinementInstruction`；
- **`footprintAggregatorData.ts`**：跨渠道工作足迹数据池，提供基于渠道（飞书、微信、桌面端、WebUI、CLI）与分类（代码评审、核心交付、架构决策、经验沉淀、卡点风险）的多维过滤与统计纯函数；
- **`weeklyDigestSynthesizerEngine.ts`**：周报智能合成引擎纯函数，支持基于事实证据提取业务成果、关键决策、踩坑教训与风险规划，并支持自然语言指令增量微调；
- **`useWeeklyDigestStore.ts`**：Zustand 集中式状态总线，管理足迹列表、过滤器、周报合成生命周期、交互微调历史与多端导出状态，派发 `myrm:weekly-digest-exported` 全局事件；
- **`CrossChannelFootprintFabricView.tsx`**：跨渠道上下文共享工作足迹聚合看板，支持全选/单项纳入周报控制、分类筛选与一键生成周报；
- **`WeeklyDigestSynthesizerModal.tsx`**：采用 HTML5 原生 `<dialog open>` 承载周报展示、风格预设切换、自然语言实时微调输入栏、一键复制 Markdown 与直落飞书文档。

## 3. 极不友好 Code Review 12 项清单遵循度
1. **零 Any**：全强类型 TypeScript 标注；
2. **零原生 Emoji**：全部采用 Lucide 矢量图标（FileText, Sparkles, Send, Copy, Check, X, Share2, Layers, ShieldCheck, Calendar, GitPullRequest 等）；
3. **前端所有 If 显式带大括号**：严格杜绝无括号写法；
4. **单文件行数严格受控**：各文件行数受控在 230 行以内（远低于 400 行红线）；
5. **a11y 无障碍标准**：采用 HTML5 原生 `<dialog open>` 模态框，遮罩层与内容分离，按钮均具备明确 `aria-label` 与 `type="button"`。
