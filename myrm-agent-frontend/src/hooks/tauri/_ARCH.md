# hooks/tauri/

Tauri 桌面端集成：runtime invoke、tray、全局快捷键桥接、应用更新、电源锁。

## 文件清单

| 文件 | 职责 |
|------|------|
| `useTauri.ts` | Tauri runtime 检测与 `invoke` 封装 |
| `useTrayStatus.ts` | Tray 图标/tooltip/任务栏进度（消费 `useLivenessState`） |
| `useTrayEvents.ts` | Tray 菜单事件路由 |
| `useInlineInputListener.ts` | 全局 Inline Input 快捷键 → FlowPad |
| `useAppshotListener.ts` | Appshot 快捷键事件桥接 |
| `useAppUpdate.ts` | Tauri 应用更新检查/下载/安装 |
| `usePowerLock.ts` | Agent 忙碌时阻止系统休眠 |

## 依赖

- `@/hooks/shell/useLivenessState` — 跨域 liveness SSOT（全部署模式）
- `@/lib/deploy-mode::isTauriRuntime` — 非 Tauri 环境 no-op
- 消费者：`components/layout/AppLayout.tsx`、`app-shell/*`、`settings/sections/system/LockedUseCard.tsx`

## 约束

- 域内相对 import；域外 `@/hooks/tauri/<file>`
- 非 Tauri 路径必须安全 no-op，不得抛错
