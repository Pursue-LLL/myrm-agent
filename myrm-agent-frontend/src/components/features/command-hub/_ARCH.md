# GlobalCmdKUniversalCommandHubAndOmniActionDispatcherSuite 架构契约与设计决策

## 1. 业务目标与核心痛点
彻底终结“用户在拥有十几个功能模块的桌面端与 WebUI 间来回通过鼠标点击左侧菜单翻找切换、AI 指令/Git 操作/系统快捷键割裂为多个独立入口”的低效人机交互瓶颈。
汲取 DeepSeek Harness 研发工作台全局效率中枢设计最优解，打造全场景无死角呼出的全局 ⌘K 效率中枢。

## 2. 核心架构设计与四大支柱
1. **全局无条件响应监听器（Global ⌘K / Ctrl+K Listener）**：
   - 无论用户当前处于哪个路由页面、光标是否聚焦在输入框，按下 `⌘K`（Windows/Linux `Ctrl+K`）即刻居中弹出毛玻璃命令面板；
   - 支持全键盘操作流：`↑` / `↓` 快速导航切换、`↵` 即刻执行、`Esc` 极速关闭。
2. **四大类动作混排与加权模糊搜索（Omni-Action Fuzzy Search）**：
   - 1）**页面导航（Navigation）**：快速跳转智能体名册、知识库、沙箱工件、系统监控等；
   - 2）**AI 快速派工（AI Dispatch）**：直接键入“让代码审查员审查当前项目”等指令快速派工；
   - 3）**通用快捷操作（Quick Actions）**：新建会话、清除上下文、导出工件等；
   - 4）**Git 运维命令（Git Operations）**：查看工作区状态、提交变更等。
3. **最近使用历史置顶推荐（Recent History Prioritization）**：
   - 记录用户最近高频触发的命令，空搜索状态下置顶展示，支持秒级复用。
4. **分类筛选徽章栏（Category Filter Bar）**：
   - 支持单键一键筛选特定类别的命令集合。

## 3. 质量指标与红线守护
- 单文件代码行数严格控制在 210 行以内（远低于 400 行硬顶）；
- 零 `any`，全面采用 TypeScript 静态强类型；
- 零原生 emoji，统一采用 Lucide 矢量图标；
- 所有 `if` 条件逻辑包裹完整大括号；
- a11y 原生 `<dialog open aria-modal="true">` 嵌套 `<section role="document">`，零控制台警告与报错。
