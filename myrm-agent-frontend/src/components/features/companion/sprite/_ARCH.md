# companion/sprite/

桌宠精灵渲染：Canvas 精灵引擎 + Tauri 桥接 + 状态机。

| 文件 | 职责 |
|------|------|
| `SpriteRenderer.tsx` / `SpriteEngine.ts` | Canvas 动画引擎 |
| `PetOverlay.tsx` | 覆盖层定位与交互 |
| `PetStateMachine.ts` / `petStateMapping.ts` | 宠物状态映射 |
| `tauriPetBridge.ts` | 桌面端 IPC 桥 |
