# eval-lab/hooks/

## 架构概述

评测流状态机：每条评测流一个 hook，封装数据获取、SSE 进度订阅与启动/中止动作，供门面 `EvalLabDashboard.tsx` 装配。

## 文件清单

| 文件                  | 地位 | 职责                                                                 | I/O/P |
| --------------------- | ---- | -------------------------------------------------------------------- | ----- |
| `useCasesEval.ts`     | 核心 | 单评测流：cases 草稿、`/eval/stream` SSE 进度、报告与历史、WBBench 运行/下载、diff 视图 | ✅ |
| `useMatrixEval.ts`    | 核心 | 矩阵 + 分层评测流：`/eval/matrix/stream` SSE、`startMatrix`/`startLayer`/`abort`       | ✅ |
| `useMemoryAbEval.ts`  | 核心 | Memory A/B 评测流：`/eval/memory-ab/stream` SSE、`start`/`abort`                        | ✅ |

## 依赖

- `@/lib/api`、`@/store/*`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
