# copilot/

## 架构概述

Lean Co-Pilot v1：Run Observer（确定性 run digest）+ Session Advisor（旁路只读问答）。不进入主 transcript；与 `companion/` 桌宠分离。

## 文件清单

| 文件                      | 地位 | 职责                                                               | I/O/P |
| ------------------------- | ---- | ------------------------------------------------------------------ | ----- |
| `RunStatusChip.tsx`       | 组件 | 主对话顶栏运行状态 chip：步骤摘要、展开 recent steps、打开 Advisor | ✅    |
| `SessionAdvisorPanel.tsx` | 组件 | 右侧 Sheet 旁路问答；Tier-0/1 由 server `advisor_service` 决定     | ✅    |

## 依赖

- `@/services/copilot` — REST client
- `@/hooks/copilot/useRunDigest` — SSE `run-digest-updated` + 初始 GET
- 宿主：`ChatWindow.tsx`、`MobileStatusBoard.tsx`；Slash `/ask`/`/side` 经 `copilot-open-advisor` 事件打开
- 划词：`QuoteToolbar.tsx` run 中「旁路提问」→ 带 `selection` 打开 Advisor（主 Chat `MessageBox`）；Mobile CC run 中经 `MobileStatusBoard`「查看完整对话」跳转主 Chat，不在 CC 复制 toolbar
