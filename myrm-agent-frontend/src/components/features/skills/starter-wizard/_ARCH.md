# Post-Install Interactive Starter Wizard & One-Click Automation Hosting Architecture

## 1. 业务目标与第一性原理
面向普通非技术与 GUI 用户，消除技能安装后“像个黑盒、不知道怎么下任务、目标参数总打错、定时配置门槛高”的上手鸿沟。
替代传统毫无信息的 Toast，原地展开沉浸式体验向导卡。

## 2. 核心架构设计
1. **受控本地嗅探候选器（Local Resource Sniffer）**：
   - `LocalResourceSnifferDropdown.tsx`
   - 自动嗅探本地微信活跃群聊、本地研发 Git 代码仓等实体，直接以下拉列表和推荐徽章呈现，杜绝用户打错名称或遗漏参数。
2. **场景精炼参数填单（Parameter Form Wizard）**：
   - `ParameterFormWizard.tsx`
   - 根据技能 Schema 动态渲染时间窗口（昨日全天/最近3天）与业务视角（群主治理/讲师教学/销售线索/干货提取）胶囊点选组。
3. **即刻单填试跑沙盒（One-Click Trial Run）**：
   - `OneClickTrialRunPanel.tsx`
   - 提供【立即试跑一次】按钮，执行极速抽样分析，实时呈现产物预览卡片、耗时与提炼条目计数，建立确定感。
4. **一键委托定时后台静默托管（One-Click Routine Scheduler）**：
   - `OneClickRoutineSchedulerCard.tsx`
   - 单击【开启每天早上 08:00 自动生成】开关，一键在后台注册高韧性 Cron 蓝图，支持主会话/系统通知/Webhook 渠道无缝推送。

## 3. 质量指标与安全红线
- 单文件行数全面受控在 200 行以内；
- 零 `any`，完备强类型 TypeScript；
- 零原生 emoji，全采用 Lucide 矢量图标；
- 严格遵循语义化 HTML 与无障碍规范。
