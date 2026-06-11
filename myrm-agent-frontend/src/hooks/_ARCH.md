# hooks/

## 架构概述

React 自定义 Hooks：连接 UI 与 `@/store`、`@/services`、`@/lib`。按域单文件或小目录组织；**禁止**桶导出（barrel index），`tasks/index.ts` 为唯一允许的桶入口。

## 域划分

| 路径 / 模式 | 职责 |
|-------------|------|
| `useDiffParser.ts` | unified diff 解析（共用 cli-visualization / markdown-render-tools） |
| `useMessageInput.ts` / `useMessageQueue.ts` / `useSmoothStream.ts` | 对话输入、队列、流式渲染 |
| `useAgentEditor.ts` / `useAgentConfigPanel.ts` / `use-agent-config-panel/` | Agent 配置面板 |
| `usePendingApprovalsRecovery.ts` | 启动/SSE 重连时从 `GET /approvals` 恢复全局 Drawer 队列（不含后台 growth draft，server 已过滤） |
| `useToolApprovalResolve.ts` / `useVisualApprovalSnapshot.ts` / `useVisualApprovalOsOverlay.ts` | 工具审批与可视化 HITL（OsOverlay 依赖 snapshot screen 元数据） |
| `useVoiceSession.ts` / `useRealtimeVoice.ts` / `useTTS.ts` | 语音会话与 TTS |
| `useGlobalShortcuts.ts` | 全局键盘快捷键（Cmd+N 新建会话、Cmd+1~9 置顶跳转，平台差异化 Shift 适配） |
| `useTauri*.ts` / `useTray*.ts` / `useAppUpdate.ts` | 桌面端 Tauri 集成 |
| `useSubscription.ts` / `useEntitlements.ts` / `useQuotaGuard.ts` | SaaS 配额与 entitlements |
| `useSystemConfig.ts` / `usePersonalSettings.ts` / `useMCPConfig.ts` | 设置与 MCP 配置状态 |
| `useMcpSecurityGate.ts` | MCP 统一安全门禁（`gateMcpEnable` / `gateMcpConfig` / batch） |
| `globalEvents/` | 全局事件 toast（记忆操作、locator healed 等） |
| `tasks/` | 后台任务 WebSocket 订阅 |
| `__tests__/` | Hook 单元测试 |

## 依赖

- `@/store/*` — Zustand 状态
- `@/services/*` — REST/SSE 客户端
- `@/lib/*` — 纯函数与常量

## 约束

- Hook 内不写 UI JSX（除 `globalEvents/*.tsx` 等 toast 渲染例外）。
- 单文件 >400 行应拆分子 hook 或下沉逻辑到 `@/lib`。
