# chat-window/approval/

可视化工具审批（HITL）子视图：Shell、浏览器会话、编辑/移交模式与屏幕高亮。

| 文件 | 职责 |
|------|------|
| `VisualApprovalRequestRenderer.tsx` | 审批请求主渲染 |
| `BrowserSessionView.tsx` / `ShellCommandDisplay.tsx` | 浏览器/命令上下文 |
| `EditModeView.tsx` / `HandoverModeView.tsx` / `RejectModeView.tsx` | 审批模式 UI |
| `VisualApprovalHighlight.tsx` / `VisualApprovalAttentionBar.tsx` | 屏幕高亮与注意力条 |
| `AllowAlwaysConfirmDialog.tsx` | 「始终允许」确认 |
