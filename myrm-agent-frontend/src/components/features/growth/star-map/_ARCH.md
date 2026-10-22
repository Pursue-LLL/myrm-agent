# Agent Growth Journey Star Map Suite (`growth/star-map`)

## 1. 架构定位与业务痛点
针对此前 `/journey` 页面仅有平铺列表、技能演化与记忆碎片分裂呈现，用户无法一眼看清 AI 长期自学习轨迹与知识资产全貌的体验短板，本模块对标 NousResearch Hermes v0.21.0 `/journey` 与 Desktop Memory Graph / Star Map 优秀设计，构建技能实体与记忆统一学习星图视图、径向时间布局、分桶回放拖动条、星图图片导出与节点就地溯源套件。

## 2. 模块拓扑与职责划分
- **`starMapTypes.ts`**：强类型定义星图节点 `StarMapNode`（金星为技能实体，蓝钻为记忆单元）、溯源连线 `StarMapLink`、分桶直方图 `TimeBucket`、多维过滤器 `StarMapFilter`（支持脱敏模式）与回放状态机 `StarMapPlaybackState`；
- **`starMapRadialMath.ts`**：径向同心圆布局计算纯函数，实现“最老居于中心，最新位于外环”的 Recency 映射、黄金角极坐标离散分布算法，以及直方图分桶统计与时间游标截断函数；
- **`starMapCatalogData.ts`**：内置真实学习信号的技能实体与记忆数据源，提供基于实战召回口径（`used` / `learned`）、实体类型、智能体作用域与时间窗口的过滤纯函数；
- **`useStarMapStore.ts`**：Zustand 集中式状态总线，管理节点与连线状态、时间游标拖拽与倍速自动回放、就地溯源抽屉状态与星图图片导出，派发 `myrm:star-map-image-exported` 全局事件；
- **`RadialStarMapCanvas.tsx`**：SVG/CSS 径向同心圆学习星图画布，渲染时间同心环、实体金星/蓝钻、连线光晕、脱敏模式切换（隐藏文字）以及无手势依赖的无障碍替代列表视图（Hermes FOS-8 规范）；
- **`StarMapPlaybackController.tsx`**：分桶双色直方图时间回放条，支持 1x/2x/5x 变速自动回放、进度滑块任意拖拽与时间截断点亮；
- **`StarMapNodeDetailSheet.tsx`**：原生 `<dialog open>` 就地溯源抽屉，展示召回次数、创建时间、来源会话跳转链接、知识标签与关联演化星图节点。

## 3. 极不友好 Code Review 12 项清单遵循度
1. **零 Any**：全强类型 TypeScript 标注；
2. **零原生 Emoji**：全部采用 Lucide 矢量图标（Star, Sparkles, Eye, EyeOff, Download, List, Layers, Play, Pause, RotateCcw, Clock, ShieldCheck 等）；
3. **前端所有 If 显式带大括号**：严格杜绝无括号写法；
4. **单文件行数严格受控**：各文件行数受控在 260 行以内（远低于 400 行红线）；
5. **a11y 无障碍标准**：采用 HTML5 原生 `<dialog open>` 模态抽屉，遮罩层与内容分离，按钮均具备明确 `aria-label` 与 `type="button"`，提供无障碍列表视图模式。
