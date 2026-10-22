# TemplateBot Marketplace & P0 Urgency Cruise Control Architecture (`templates/template-bot`)

## 1. 架构定位与业务痛点
针对用户在创建专属 AI 团队时面对空白配置表单无从下手、缺乏岗位上下游协作分工最佳实践，以及突发最高优先级紧急长任务（如生产事故、宕机突击、紧急财报攻坚）时缺乏高频看门狗纠偏机制导致 Agent 容易陷入死循环或跑偏的深层痛点，本模块对标 SpaceXAI Grok Bot，提供预制岗位智能体模板市场（TemplateBot Hub）、一键克隆团队架构预设与 P0 紧急高频纠偏巡航控制面板。

## 2. 模块拓扑与职责划分
- **`templateBotTypes.ts`**：定义岗位角色契约 `TemplateBotRole`、团队架构预设 `TeamRosterTemplate`、P0 紧急巡航控制状态机 `P0UrgencyCruiseState` 与看门狗巡检日志模型；
- **`templateBotCatalog.ts`**：内置 6 大垂直岗位模板（首席幕僚长、资深架构师、全栈工程师、深度研究员、财务分析师、质量总监）与 3 套完整协同团队预设（全栈工程突击队、商业技术情报团队、高可靠生产守护团队），并提供多维检索纯函数；
- **`p0UrgencyWatchdogEngine.ts`**：P0 紧急纠偏逻辑纯函数引擎，支持自然语言意图判定（“这是 P0 任务”）、近程轨迹死循环与工具重复调用偏离审查、自动生成原地注入 Steering 指令；
- **`useTemplateBotStore.ts`**：Zustand 集中式状态总线，管理模板市场弹窗、分类搜索、单角色实例化、团队克隆与 P0 紧急模式生命周期，派发 `myrm:p0-urgency-activated` 与 `myrm:p0-steering-injected` 全局事件；
- **`TemplateBotMarketplaceModal.tsx`**：岗位模板市场大盘弹窗，支持分类筛选、团队预设一键克隆与单岗位一键实例化；
- **`P0UrgencyCruiseControlPanel.tsx`**：会话输入框常驻 P0 紧急巡航控制面板，提供 5 分钟看门狗倒计时条、偏离拦截计数、手动巡检触发与巡检日志折叠抽屉。

## 3. 极不友好 Code Review 12 项清单遵循度
1. **零 Any**：全强类型契约；
2. **零原生 Emoji**：全部采用 Lucide 矢量图标；
3. **前端所有 If 显式带大括号**：严格杜绝无括号单行写法；
4. **单文件行数严格受控**：各文件行数受控在 260 行以内（远低于 400 行红线）；
5. **a11y 无障碍标准**：符合 HTML5 语义化（采用原生 dialog 标签）、键盘交互与触控目标尺寸。
