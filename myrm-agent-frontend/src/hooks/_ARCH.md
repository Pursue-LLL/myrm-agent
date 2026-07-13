# hooks/

## 架构概述

React 自定义 Hooks：连接 UI 与 `@/store`、`@/services`、`@/lib`。按域单文件或小目录组织；**禁止**桶导出（barrel index），`tasks/index.ts` 为唯一允许的桶入口。

## 域划分

| 路径 / 模式 | 职责 |
|-------------|------|
| `useDiffParser.ts` | unified diff 解析（共用 cli-visualization / markdown-render-tools） |
| `useMessageInput.ts` / `useMessageQueue.ts` / `useSmoothStream.ts` | 对话输入、队列、流式渲染 |
| `useInputHistory.ts` | 输入历史回溯（ArrowUp 空框触发、per-agent localStorage 隔离、ghost placeholder、弹窗键盘导航） |
| `useInputFileUpload.ts` | 聊天输入文件上传（粘贴图片、拖拽文件、SHA-256 去重；支持 image/video/audio 分级大小校验） |
| `useAgentEditor.ts` / `useAgentConfigPanel.ts` / `use-agent-config-panel/` | Agent 配置面板 |
| `usePendingApprovalsRecovery.ts` | 启动/SSE 重连时从 `GET /approvals` 恢复全局 Drawer 队列（不含后台 growth draft，server 已过滤） |
| `useToolApprovalResolve.ts` / `useVisualApprovalSnapshot.ts` / `useVisualApprovalOsOverlay.ts` | 工具审批与可视化 HITL（OsOverlay 依赖 snapshot screen 元数据） |
| `useVoiceSession.ts` / `useRealtimeVoice.ts` / `useGeminiLiveVoice.ts` / `useTTS.ts` | 语音会话与 TTS（useVoiceSession 含 PTT 屏幕上下文融合，支持 OpenAI Realtime WebRTC + Gemini Live WebSocket 双 Provider；useTTS API 模式在 503/422 时 toast 提示；ReadAloud API 模式受 voice_interaction feature gate） |
| `useVoicePttListener.ts` | Tauri 全局语音 PTT 快捷键事件桥接（IPC → DOM CustomEvent），含 PTT 屏幕上下文转发 |
| `useSlashCommand.ts` | Slash 命令面板 Hook（`/` 触发检测 + 模糊搜索 + 键盘导航 + 命令执行；合并系统行为、用户命令、Agent 绑定技能） |
| `useGlobalShortcuts.ts` | 全局键盘快捷键（Cmd+N 新建会话、Cmd+1~9 置顶跳转，平台差异化 Shift 适配） |
| `useTauri*.ts` / `useTray*.ts` / `useAppUpdate.ts` | 桌面端 Tauri 集成 |
| `useLivenessState.ts` | 全局 Agent liveness SSOT：轮询 `/health/liveness` API 提供 busy/idle/degraded 三态，供 tray、Pet、tab badge 消费 |
| `useTrayStatus.ts` | Tauri tray icon/tooltip/taskbar 进度条：消费 `useLivenessState` 全局三态 + `/background-tasks` running 数驱动图标切换；hidden 窗口时 busy→idle 转换触发 `requestUserAttention`（仅 Tauri） |
| `useTabBadge.ts` | Tab title 状态前缀：消费 `useLivenessState` 在 `document.title` 添加 `[*]`/`[!]` 前缀，与审批闪烁协调让步（全部署模式） |
| `useWhatsNew.ts` | 版本变更感知：启动时对比 localStorage 已查看版本与当前版本，变更时从 GitHub Release API 拉取 Release Notes |
| `useSubscription.ts` / `useEntitlements.ts` / `useQuotaGuard.ts` | SaaS 配额与 entitlements |
| `useBillingCatalog.ts` | CP 公开定价 catalog |
| `useSessionWuBurnTracker.ts` | 任务结束 WU 消耗提示 |
| `useSystemConfig.ts` / `usePersonalSettings.ts` / `useMCPConfig.ts` | 设置与 MCP 配置状态；`useSystemConfig` 在 save/reset/saveAndRestart 时同步 `myrm-tauri-system-config` 供 `deploy-mode` 读端口 |
| `useMcpSecurityGate.ts` | MCP 统一安全门禁（`gateMcpEnable` / `gateMcpConfig` / batch） |
| `useNavBadges.ts` | NavBar badge 数据（cron failures、approvals、notifications、extension 连接状态）+ SSE 驱动刷新 |
| `globalEvents/` | 全局事件 toast（记忆操作、locator healed 等） |
| `tasks/` | 后台任务 WebSocket 订阅 |
| `__tests__/` | Hook 单元测试 |
| `useWidgetStorage.ts` | Widget iframe localStorage polyfill 宿主侧桥接（debounce+batch 持久化） |

## 依赖

- `@/store/*` — Zustand 状态
- `@/services/*` — REST/SSE 客户端
- `@/lib/*` — 纯函数与常量

## 约束

- Hook 内不写 UI JSX（除 `globalEvents/*.tsx` 等 toast 渲染例外）。
- 单文件 >400 行应拆分子 hook 或下沉逻辑到 `@/lib`。
- 桶导出政策见根 [_ARCH.md](../../_ARCH.md)「桶导出政策」表。
