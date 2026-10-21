# hooks/approval/

工具审批（HITL）与浏览器 takeover 动作。

| 文件                             | 职责                                                                                                                                                                                                          |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `usePendingApprovalsRecovery.ts` | 启动/SSE 重连恢复审批队列                                                                                                                                                                                     |
| `useToolApprovalResolve.ts`      | 单条/bulk approve/reject + SSE resume；path-ASK grantDirectory 后 `refreshSessionAccessRoots`；被风控拦下的理由（`RiskBlockedError`）让审批卡留着、已键入的理由不丢，也不叠加失败提示（风控提示已由事件弹出） |
| `useVisualApprovalSnapshot.ts`   | pending visual 审批自动拉 snapshot（`fetchSnapshot(true)`，标记为 turn 视图：turn 结束时随 ownership 一并回收，避免幽灵视图残留）                                                                             |
| `useVisualApprovalOsOverlay.ts`  | Tauri OS 红框 overlay 生命周期                                                                                                                                                                                |
| `useBrowserTakeoverActions.ts`   | Extension/VNC browser HITL Done/Skip                                                                                                                                                                          |

依赖：`@/lib/approval/*`、`@/store/useApprovalStore`。消费者：`chat-window/`、`components/approval/`、`VisualDesktopToggle`。
