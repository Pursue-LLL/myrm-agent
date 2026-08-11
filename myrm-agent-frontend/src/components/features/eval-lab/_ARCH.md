# eval-lab/

## 架构概述

评测实验室：批量用例、结果对比（开发/实验向）。支持单配置评测、跨配置矩阵对比评测与 Memory A/B 评测（记忆开/关对比）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `EvalLabDashboard.tsx` | 核心 | 评测用例批量运行、结果对比与历史记录仪表盘。支持多 Profile 选择：选 1 个走单配置评测，选 2+ 自动切换为矩阵对比模式。含 Memory A/B Tab：订阅 `/eval/memory-ab/stream` SSE 展示开/关记忆对比评测进度，复用 `MatrixResultView` 渲染对比报告，并联动全局运行/中止按钮状态（`memoryAbRunning` 期间禁用矩阵与 WBBench 操作）。报告明细表逐用例展示 verdict（通过/失败）、token 消耗、耗时、Rule 判分明细（pass_rate 徽标 + 通过/总数）与断言失败详情。 | ✅ |
| `WbBenchSources.tsx` | 展示 | 外部基准数据集源面板（统一 catalog：WorkBuddy Bench 四赛道 + BrowseComp 等注册第三方基准）：卡片展示评分模式徽标（native/composite/llm_judge）、下载状态、任务数、归档大小、本地大小与最近一次报告（诚实区分“已评分通过率”与“评分待定”，避免将未评分误显为 0%）。数据源 `GET /eval/benchmarks`，下载按钮走 `POST /eval/benchmarks/download`，运行走 `POST /eval/benchmarks/run` 后台评测（复用 Eval Lab 的评测进度 SSE 与报告 tab），卡片内实时显示下载进度条；`supports_memory_ab` 为 true 时提供“Memory A/B”按钮（`POST /eval/memory-ab/run`），点击先弹确认对话框提示「需要 embedding 模型」与「基准多为单轮任务、记忆收益在长会话更明显」，避免用户误解读结果。 | ✅ |
| `MatrixResultView.tsx` | 展示 | 矩阵评测结果视图：per-profile 汇总 + Case×Profile 网格热力图，色彩编码稳定/回归/全失败。Memory A/B 报告额外展示每臂 `memory_tool_calls`（记忆工具实际调用次数，任一臂有该字段时动态显示该列，用于判断记忆是否真正被参与）。 | ✅ |
| `MemoryAbHistoryTable.tsx` | 展示 | Memory A/B 历史报告列表：按时间倒序展示历史运行的通过率与记忆工具调用次数，支持选中某次历史报告回看（高亮当前项），点击查看触发 `GET /eval/memory-ab/reports/{timestamp}` 加载报告。空历史时不渲染。 | ✅ |
| `CaseFormatReference.tsx` | 辅助 | 用例格式参考面板：展开/收起的断言类型说明表格。 | ✅ |

## 测试覆盖

- 单测（Vitest）：`__tests__/WbBenchSources.test.tsx` 覆盖 WBBench 卡片渲染、评分徽标、下载/运行按钮，以及 Memory A/B 按钮 + 确认对话框（取消/确认调用 `onMemoryAb`）；`__tests__/MemoryAbHistoryTable.test.tsx` 覆盖历史表渲染（per-arm pass-rate + `memory_tool_calls`）与选中回看。
- Chrome E2E（`tests/e2e/test_memory_ab_chrome_e2e.py`）：卡片入口 + 确认对话框取消（READ）；预置报告渲染双臂矩阵 + Run History + 点击历史加载（NAMESPACE_WRITE）；真实 run 启动 + Stop abort（NAMESPACE_WRITE）。

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
