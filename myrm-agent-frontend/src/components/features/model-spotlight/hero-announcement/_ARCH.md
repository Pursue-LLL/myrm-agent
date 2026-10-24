# Hero Model Release Spotlight & Motion Announcement Suite (`model-spotlight/hero-announcement`)

## 1. 架构定位与业务痛点
针对重大前沿模型发布（如 GPT-6 Astra、Claude 3.7 Hybrid Thinking、DeepSeek-V3 Reasoning）或平台重磅折扣上线时，传统 AI 平台仅在更新日志中静默呈现，普通用户毫无感知、手动配置复杂门槛高的体验短板，本模块提供前沿模型微动效聚光灯横幅、一键热试用轻量沙箱与一键热挂载当前智能体套件。

## 2. 模块拓扑与职责划分
- **`modelSpotlightTypes.ts`**：强类型定义模型聚光灯实体 `SpotlightModelItem`、基准测试指标 `BenchmarkMetric`、试用消息流 `PlaygroundMessage`、热挂载对比视图 `MountComparison` 与忽略记录 `DismissRecord`；
- **`spotlightCatalogData.ts`**：提供前沿模型基准规格数据池，以及上下文格式化 `formatTokenCount`、热挂载差异对比 `computeMountComparison`、已忽略过滤 `filterAvailableSpotlights` 等纯函数；
- **`useModelSpotlightStore.ts`**：Zustand 集中式状态总线，管理活跃聚光灯切换、折叠状态、已忽略记录持久化、试用沙箱消息模拟与智能体热挂载，派发 `myrm:model-hot-mounted` 全局事件；
- **`HeroSpotlightMotionBanner.tsx`**：顶部/浮动微动效聚光灯横幅，基于半透明磨砂玻璃质感设计，呈现模型亮点徽章、上下文容量与跑分胶囊，支持多模型 Tab 切换、折叠和关闭；
- **`SpotlightPlaygroundModal.tsx`**：一键热试用轻量临时沙箱，使用语义化 `<dialog open>`，支持预设基准 Prompt 快捷测试、即时响应测速徽章与无损会话清空；
- **`SpotlightMountConfirmModal.tsx`**：一键热挂载当前智能体确认模态框，直观呈现当前模型与目标模型在上下文容量、费率预算及多模态/推理能力的对比，提供无损热挂载保障机制。

## 3. 极不友好 Code Review 12 项清单遵循度
1. **零 Any**：全强类型 TypeScript 标注；
2. **零原生 Emoji**：全部采用 Lucide 矢量图标（Sparkles, Zap, Play, Cpu, TrendingUp, CheckCircle2, ShieldCheck 等）；
3. **前端所有 If 显式带大括号**：严格杜绝无括号写法；
4. **单文件行数严格受控**：各文件行数受控在 250 行以内（远低于 400 行红线）；
5. **a11y 无障碍标准**：采用 HTML5 原生 `<dialog open>` 模态框，遮罩层与内容分离，按钮均具备明确 `aria-label` 与 `type="button"`。
