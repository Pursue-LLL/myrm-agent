# eval-lab/tabs/

## 架构概述

评测实验室的 tab 专属展示组件。每个 tab 为纯展示，状态由 `hooks/` 中的评测流提供。

## 文件清单

| 文件                    | 地位 | 职责                                                   | I/O/P |
| ----------------------- | ---- | ------------------------------------------------------ | ----- |
| `CasesTab.tsx`          | 核心 | 用例编辑 tab：格式参考 + JSON 编辑器（草稿绑定）        | ✅    |
| `ReportTab.tsx`         | 核心 | 单评测报告 tab：进度、通过率统计、环境披露与逐用例明细  | ✅    |
| `MatrixTab.tsx`         | 核心 | 矩阵/分层报告 tab：进度 + 结果视图 + 历史回看           | ✅    |
| `MemoryAbTab.tsx`       | 核心 | Memory A/B 报告 tab：进度 + 双臂结果 + 历史回看         | ✅    |
| `HistoryTab.tsx`        | 核心 | 单评测历史 tab：通过率趋势与历史记录表                  | ✅    |
| `SkillAbTab.tsx`        | 核心 | 技能 A/B 报告 tab                                      | ✅    |
| `EvalRunProgress.tsx`   | 辅助 | 矩阵与 Memory A/B 共享的运行中进度视图                 | ✅    |

## 依赖

- `../components/`、`../hooks/`、`@/components/primitives/*`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
