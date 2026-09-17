# chat/

## 架构概述

对话核心与辅助交互组件。包含任务预算徽标与动态偏好拟合雷达抽屉。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `DynamicPreferenceRadarDrawer.tsx` | 核心 | 用户动态偏好雷达拟合看板抽屉。纯 SVG 多边形几何渲染、5 维偏好滑块微调、锁定态保护与重置基准。 | ✅ |
| `TaskBudgetPill.tsx` | 辅助 | 对话页任务预算消耗与步数状态胶囊徽标。 | ✅ |
| `index.ts` | 入口 | 对话组件导出桶。导出 `TaskBudgetPill` 与 `DynamicPreferenceRadarDrawer`。 | ✅ |
