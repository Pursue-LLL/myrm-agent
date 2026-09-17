# eval-lab/components/

## 架构概述

评测展示组件与共享工具：被 `tabs/` 与 `hooks/` 复用的报告视图、历史表与诊断面板。不含数据获取逻辑。

## 文件清单

| 文件                                        | 地位 | 职责                                                       | I/O/P |
| ------------------------------------------- | ---- | ---------------------------------------------------------- | ----- |
| `MatrixResultView.tsx`                      | 核心 | 矩阵/分层/记忆 A/B 结果视图（热力图、Δ 通过率、披露区）     | ✅    |
| `MatrixHistoryTable.tsx`                    | 核心 | 矩阵/分层历史报告列表与回看                               | ✅    |
| `MemoryAbHistoryTable.tsx`                  | 核心 | Memory A/B 历史报告列表与回看                              | ✅    |
| `BenchmarkSources.tsx`                      | 核心 | 外部基准数据集源面板（下载/运行/抽样/分层入口）             | ✅    |
| `FailureSignatureClusteringPanel.tsx`       | 核心 | 失败特征聚类与可寻址性诊断（含 JSON Patch 一键修复）        | ✅    |
| `PairedSignificancePanel.tsx`               | 核心 | 配对显著性检验面板                                         | ✅    |
| `ComponentAblationImpactRankingChip.tsx`    | 辅助 | 组件消融影响排名徽标                                       | ✅    |
| `format.ts`                                 | 工具 | 共享格式化（`formatMib` 字节大小）                          | ✅    |
| `pairedSignificanceTypes.ts`                | 类型 | 配对显著性检验类型定义                                     | ✅    |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
