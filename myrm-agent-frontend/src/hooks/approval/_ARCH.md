# hooks/approval/

工具审批（HITL）与浏览器 takeover 动作。

| 文件 | 职责 |
|------|------|
| `usePendingApprovalsRecovery.ts` | 启动/SSE 重连恢复审批队列 |
| `useToolApprovalResolve.ts` | 单条/bulk approve/reject + SSE resume |
| `useVisualApprovalSnapshot.ts` | pending visual 审批自动拉 snapshot |
| `useVisualApprovalOsOverlay.ts` | Tauri OS 红框 overlay 生命周期 |
| `useBrowserTakeoverActions.ts` | Extension/VNC browser HITL Done/Skip |

依赖：`@/lib/approval/*`、`@/store/useApprovalStore`。消费者：`chat-window/`、`components/approval/`、`VisualDesktopToggle`。
