# runs/

## 架构概述

Unified Runs Hub：聚合 Cron / Kanban / Shell 后台任务的运行历史，支持状态与来源筛选、分页加载与详情展开。Kanban run 详情区嵌入 `ExecutionTraceTimeline`（`task_id` 作 sessionId）提供完整执行轨迹回放。

## 文件清单

| 文件                            | 地位 | 职责                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | I/O/P |
| ------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `RunsHub.tsx`                   | 核心 | 运行列表 UI：筛选 Tabs、分页与加载失败态、degraded banner；列表有 running 任务时 30s 轮询自动刷新                                                                                                                                                                                                                                                                                                                                                                                                                     | —     |
| `RunRow.tsx`                    | 核心 | 单条运行：状态图标加读屏状态词（`STATUS_ICON` 与 `statusLabel` 对 `RunStatus` 穷举）、来源徽标、相对时间与时长、展开详情（输出、错误、停止原因、执行步骤；停止原因框的原文与错误块相同时只显示一遍）；头部是唯一的展开开关（原生 `button` + `aria-expanded`，展开时 `aria-controls` 指向详情区），详情区与头部平级；Kanban run 嵌入 trace（`showEvalCase={false}` + 运行中 `pollMs` 实时刷新）；cron 来源的跳过运行把输出码经 `cron-utils.skipReasonLabelKey` 显示为本地化标签（取自 `cron` namespace），不露出原始码 | —     |
| `__tests__/RunRow.test.tsx`     | 测试 | 头部开关语义（`aria-expanded`/`aria-controls`、键盘 Enter/Space）、点击输出与 trace 内按钮不收起整行、相对时间走共享格式化（晚于本机时钟的起始时间读作 now）、每种状态的图标与读屏状态词、停止原因原文不与错误文本重复、执行步骤只显示运行记录的名称                                                                                                                                                                                                                                                                  | —     |
| `__tests__/RunsHub.test.tsx`    | 测试 | error/retry、emptyFiltered、degraded、loadMore toast、badge、Kanban trace 展开、跳过运行的原因标签（经 `RunsHub` 渲染 `RunRow`）                                                                                                                                                                                                                                                                                                                                                                                      | —     |
| `__tests__/runsLocales.test.ts` | 测试 | 中英双语 `runs` namespace key 完整性                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | —     |

## 路由

| 路径    | 页面                                                |
| ------- | --------------------------------------------------- |
| `/runs` | [src/app/runs/page.tsx](../../../app/runs/page.tsx) |

## 依赖

- `@/services/runs` — `listUnifiedRuns`、`UnifiedRun` 类型（POS: 统一运行历史 REST 客户端）
- `@/components/primitives/*` — Button、Tabs、Skeleton
- `@/components/features/cron/cron-utils` — `skipReasonLabelKey`（POS: 跳过运行的输出码 → 本地化标签 key）
- `@/lib/utils/relativeTime` — `formatRelativeTime`（POS: 基于 `Intl.RelativeTimeFormat` 的 Locale 感知相对时间）
- `locales/namespaces/*/runs.json` — 运行时 `runs` namespace（中英双语：en/zh）；译者 SSOT 为 `locales/{lang}.json`，改文案后跑 `bun run i18n:split`

## 约束

- 文案禁止硬编码；使用 `useTranslations('runs')`，cron 跳过原因的标签沿用 `cron` namespace 的 `skipped*` 键，不在 `runs` 里重复一份
- 相对时间走共享的 `formatRelativeTime(iso, useLocale())`，随界面语言输出完整措辞，时间文案不放进 `runs` namespace
- 运行状态由图标加读屏状态词（`sr-only`）共同表达：状态词复用现有文案（`runs` 的筛选与停止原因键、`cron` 的 `runSkipped` / `runCircuitBreak`）；熔断（`circuit_break`）用盾牌图标与定时任务面板同款玫红，收起行不另写横幅；`RunStatus` 的取值与服务端 `app/api/runs/schemas.py` 一致，由 server 的 `test_run_status_parity.py` 校验，新增状态先改 `services/runs.ts`，再补 `STATUS_ICON` 与 `statusLabel`，漏一处编译即报错
- 整行不是按钮：展开/收起只挂在头部原生 `button` 上；详情区含 trace 回放/导出按钮和可选中的输出文本，不得放进触发收起的元素里（嵌套交互元素既破坏读屏语义，也会让点击详情内按钮时整行收起）；头部 `button` 内只放行内元素（`span`）
- 状态色文字用令牌 `text-destructive-text` / `text-warning`（亮/暗主题各自满足 4.5:1）；不要用 `text-red-500/80`、`text-amber-600/90` 这类带透明度的调色板色，亮色主题下对比度只有约 3:1；状态图标是非文字元素，亮色主题须达 3:1：成功与超时用 `emerald-600` / `amber-600`（500 档不足 3:1），暗色用 400 档
- 执行步骤只显示运行记录的 `tool_name` / `step_key`，没有记录就不渲染占位文案
- `has_execution_steps` = cron metadata 含 progressSteps **或** kanban task 有 progress_note
- Kanban run（`source === 'kanban' && task_id != null`）展开时嵌入 `ExecutionTraceTimeline sessionId={task_id}`；kanban 无 Chat 记录 → 传 `showEvalCase={false}`（避免「保存为评测用例」必然失败）
- 首屏加载失败：inline error + retry（不用 toast，避免与 inline 重复）
- 分页 loadMore 失败：toast.error（列表仍可见）
- 筛选无结果：显示 `emptyFiltered`；无筛选真空：显示 `empty`
- 部分数据源不可用：`degraded` banner（server 返回 `failed_sources`）
- 筛选切换时使用 requestSeq 丢弃过期响应，避免竞态覆盖；reload 期间列表半透明 + 禁用交互
- 新增子组件时保持本目录 `_ARCH.md` 与 [features/_ARCH.md](../_ARCH.md) 同步
