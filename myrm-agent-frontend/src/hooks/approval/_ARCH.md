# hooks/approval/

工具审批（HITL）与浏览器 takeover 动作。

| 文件                             | 职责                                                                                                                                                                                                          |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `usePendingApprovalsRecovery.ts` | 启动/SSE 重连恢复审批队列                                                                                                                                                                                     |
| `useToolApprovalResolve.ts`      | 单条/bulk approve/reject + SSE resume；path-ASK grantDirectory 后 `refreshSessionAccessRoots`；被风控拦下的理由（`RiskBlockedError`）让审批卡留着、已键入的理由不丢，也不叠加失败提示（风控提示已由事件弹出） |
| `useStagedCredentials.ts`        | 一张命令审批卡上已暂存一次性凭据的状态机：暂存 / 撤回（服务端销毁失败时保留并抛出）/ 丢弃（拒绝、命令被改写）/ 到期自动销毁并提示；状态留在卡片而非录入表单，切到编辑/拒绝视图时不丢                          |
| `useApprovalCountdown.ts`        | 审批卡倒计时：每秒刷新剩余秒数，给出是否过期、是否进入最后 10 秒与进度百分比；只计时，不决定过期后做什么                                                                                                      |
| `useVisualApprovalSnapshot.ts`   | pending visual 审批自动拉 snapshot（`fetchSnapshot(true)`，标记为 turn 视图：turn 结束时随 ownership 一并回收，避免幽灵视图残留）                                                                             |
| `useVisualApprovalOsOverlay.ts`  | Tauri OS 红框 overlay 生命周期                                                                                                                                                                                |
| `useBrowserTakeoverActions.ts`   | Extension/VNC browser HITL Done/Skip；managed 模式经 `useUserControlStore.release()` 交还控制权                                                                                                               |

依赖：`@/lib/approval/*`、`@/store/useApprovalStore`。消费者：`chat-window/`、`components/approval/`、`VisualDesktopToggle`。
