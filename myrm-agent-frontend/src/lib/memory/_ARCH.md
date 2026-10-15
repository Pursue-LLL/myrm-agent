# lib/memory/

记忆域的前端纯函数。

| 文件            | 职责                                                                                                                                                       |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `memoryLabs.ts` | `isMemoryLabsEnabled()`：Memory Command Center 与设置内实验面板的开关，读取 `NEXT_PUBLIC_MEMORY_LABS=1`（兼容 `NEXT_PUBLIC_MEMORY_LAB=1`）；调用方为 `MemorySection.tsx` 与 `MemoryCommandCenterPanels.tsx` |
