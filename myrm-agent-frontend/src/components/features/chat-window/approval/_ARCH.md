# chat-window/approval/

可视化工具审批（HITL）子视图：截图审批卡片、Shell/浏览器上下文、编辑/移交模式与屏幕高亮。

| 文件                                                               | 职责                                                                                        |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| `VisualApprovalInlineSection.tsx`                                  | 桌面聊天 inline 审批入口（消息级挂载；browser/desktop 预览经 scoped selector 按 chat 隔离） |
| `VisualApprovalRequestRenderer.tsx`                                | loading/ready/unavailable 三态路由渲染                                                      |
| `VisualApprovalArtifactCard.tsx`                                   | 截图 + BBox + 审批操作主卡片                                                                |
| `VisualApprovalPendingCard.tsx`                                    | snapshot loading 占位卡                                                                     |
| `VisualApprovalUnavailableCard.tsx`                                | snapshot 失败降级 + 重试                                                                    |
| `VisualApprovalHighlight.tsx`                                      | 红框 overlay 高亮                                                                           |
| `VisualApprovalAttentionBar.tsx`                                   | 滚动区外 pending 可达条                                                                     |
| `VisualApprovalOsOverlaySync.tsx`                                  | Tauri OS overlay 生命周期同步（scoped browser + desktop viewData）                          |
| `BrowserSessionView.tsx` / `ShellCommandDisplay.tsx`               | 浏览器/命令上下文                                                                           |
| `EditModeView.tsx` / `HandoverModeView.tsx` / `RejectModeView.tsx` | 审批模式 UI（Edit 含 pattern 预览与时效阶梯配置）                                           |
| `AllowAlwaysConfirmDialog.tsx`                                     | 「始终允许」确认（支持 pattern 预览与 Session/15m/1h/Permanent 时效阶梯门禁）               |
| `IntentEnvelopeCard.tsx`                                           | Pre-flight 前瞻意图执行包络线授权卡片（约定目标应用白名单、执行步数预算与敏感凭证边界声明）  |
| `LeaseProgressCapsule.tsx`                                         | 执行态配额进度 HUD 胶囊（显示剩余步数配额并在临近用尽时提供原地一键快捷续期）                |
| `__tests__/AllowAlwaysConfirmDialog.test.tsx`                      | 单元测试：覆盖时效阶梯与高危永久授权防呆警示                                                |
| `__tests__/EditModeView.test.tsx`                                  | 单元测试：覆盖 EditModeView 时效阶梯选择与确认回调行为                                      |
| `__tests__/IntentEnvelopeCard.test.tsx`                            | 单元测试：覆盖前瞻授权卡片渲染、激活包络线与原地租期续期状态流转                             |
