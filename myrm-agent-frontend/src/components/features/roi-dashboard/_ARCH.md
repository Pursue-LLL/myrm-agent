# roi-dashboard/

## 架构概述

智能体可量化 ROI 生产力大盘与已节省时间价值看板 (`AgentMeasurableRoiAndDailyTimeSavedHUD`, Item 51 P0)。
彻底解决 OpenClaw 式生活助理跑完一天“省下来的时间不够配置花的时间、花了几十刀 Token 不知值不值”的价值感缺失痛点。
提供显性化已节省工时看板（今日/本周/累计）、投入产出比对比（替代人工工时价值 vs 实际算力成本）、任务类别贡献分解、高收益开箱即用工作流目录以及周度生产力里程碑战报。

## 文件清单

| 文件名 | 类型 | 职责 | 状态 |
| :--- | :--- | :--- | :--- |
| `roiTypes.ts` | 类型 | 领域契约（RoiTimeRange、CategorySavingsItem、WeeklyDigestSpec、RoiMetricsSnapshot、HighYieldRoutineSpec 等） | ✅ |
| `roiService.ts` | 服务 | 客户端 API 适配器（向 `/api/v1/system/roi/*` 发起请求，具备离线本地精准计算回退） | ✅ |
| `RoiValueDashboardCard.tsx` | 组件 | 生产力核心仪表盘卡片（工时切换、小时数大屏、价值 vs 成本对比条、ROI 乘数、任务类别分布与周度战报弹窗） | ✅ |
| `HighYieldRoutineCatalog.tsx` | 组件 | 开箱即用高收益工作流预置目录（竞品动态雷达、群聊待办提取、代码诊断、财报指标萃取一键启动） | ✅ |
| `index.ts` | 门面 | 统一导出所有类型、服务与视图组件 | ✅ |

## 依赖关系

- 内部：`./roiTypes`、`./roiService`、`./RoiValueDashboardCard`、`./HighYieldRoutineCatalog`
- 外部：`lucide-react`、`next-intl`、`@/lib/api`
