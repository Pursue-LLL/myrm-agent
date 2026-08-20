# companion/sprite/

桌宠精灵渲染：Canvas 精灵引擎 + Tauri 弹出层（PSUA）+ 状态机。

| 文件                                                                   | 地位 | 职责                                                                                                         | I/O/P |
| ---------------------------------------------------------------------- | ---- | ------------------------------------------------------------------------------------------------------------ | ----- |
| `SpriteEngine.ts` / `SpriteRenderer.tsx`                               | 核心 | Canvas 2D 精灵图渲染                                                                                         | ✅    |
| `PetOverlay.tsx`                                                       | 核心 | 主窗口嵌入层 UI + 右键菜单                                                                                   | ✅    |
| `usePetSurfaceHost.ts`                                                 | 核心 | Tauri 外置窗生命周期 + IPC 同步                                                                              | ✅    |
| `PetOverlayWindowApp.tsx`                                              | 核心 | `/pet-overlay` 傀儡窗（气泡/composer/mail/alpha 穿透）                                                       | ✅    |
| `PetStatusBubble.tsx` / `petStatusBubbleSpec.ts`                       | 辅助 | 外置窗状态气泡文案；tone 色从 `companionTheme.ts` token 派生                                                 | ✅    |
| `petSurfaceBridge.ts`                                                  | 辅助 | Tauri IPC + event 桥                                                                                         | ✅    |
| `petSurfaceTypes.ts` / `petSurfaceStorage.ts`                          | 辅助 | IPC 类型 + 持久化                                                                                            | ✅    |
| `petSurfaceAwayCompletion.ts` / `usePetSurfaceUnread.ts`               | 辅助 | 离屏完成 → mail 未读                                                                                         | ✅    |
| `petOverlayLayoutStorage.ts`                                           | 辅助 | 嵌入层位置/尺寸 localStorage                                                                                 | ✅    |
| `PetStateMachine.ts` / `deriveBlockedOnUser.ts` / `petStateMapping.ts` | 核心 | 7 态 + HITL blocked SSOT；SSE 含 `moa_overlay_active` / `moa_ref_done`（MoA overlay 与 legacy consensus 键） | ✅    |

路由：`src/app/pet-overlay/`（Tauri 透明置顶 webview 入口）。
