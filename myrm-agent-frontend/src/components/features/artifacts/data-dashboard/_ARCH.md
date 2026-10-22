# Dynamic Web Dashboard Architecture (`data-dashboard`)

## 模块定位
负责零显式提示意图自触发可视化与多维表格动态 Web 看板渲染引擎（Item 49 P1 · 汲取豆包可视化技能与妙搭数据看板亮点）。
支持自动解析多维数据与 JSON 规格，呈现 KPI 环比卡片、动态折线/柱状图切换、透视表格快速检索，并支持离线自包含单文件 HTML 导出。

## 文件职责清单

| 文件名 | 类型 | 职责说明 | 状态 |
| :--- | :--- | :--- | :--- |
| `dataDashboardTypes.ts` | 类型 | 领域类型定义：DashboardSpec, KpiMetric, ChartConfig, TableSpec 等 | ✅ |
| `dataDashboardUtils.ts` | 工具 | CSV 与 JSON 容错解析为统一规格，生成独立离线 HTML 看板文件 | ✅ |
| `InteractiveDashboardArtifact.tsx` | 组件 | 高颜值数据看板渲染器，支持 KPI 网格、图表形态切换、明细表搜索与全屏交互 | ✅ |
| `index.ts` | 门面 | 统一导出类型、工具与组件 | ✅ |
| `_ARCH.md` | 文档 | 模块定位与架构清单 | ✅ |
