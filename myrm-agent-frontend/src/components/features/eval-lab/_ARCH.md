# eval-lab/

## 架构概述

评测实验室：批量用例、结果对比（开发/实验向）。支持单配置评测和跨配置矩阵对比评测。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `EvalLabDashboard.tsx` | 核心 | 评测用例批量运行、结果对比与历史记录仪表盘。支持多 Profile 选择：选 1 个走单配置评测，选 2+ 自动切换为矩阵对比模式。 | ✅ |
| `MatrixResultView.tsx` | 展示 | 矩阵评测结果视图：per-profile 汇总 + Case×Profile 网格热力图，色彩编码稳定/回归/全失败。 | ✅ |
| `CaseFormatReference.tsx` | 辅助 | 用例格式参考面板：展开/收起的断言类型说明表格。 | ✅ |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
