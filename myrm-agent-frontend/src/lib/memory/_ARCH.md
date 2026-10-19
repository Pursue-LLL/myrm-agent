# lib/memory/

记忆域的前端纯函数。

| 文件                | 职责                                                                                                                                                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `memoryLabs.ts`     | `isMemoryLabsEnabled()`：Memory Command Center 与设置内实验面板的开关，读取 `NEXT_PUBLIC_MEMORY_LABS=1`；调用方为 `MemorySection.tsx` 与 `MemoryCommandCenterUnderstandSection.tsx`                                       |
| `importWarnings.ts` | `resolveImportWarning(warning, t)`：记忆导入告警码 → `memory.importWarnings` 文案，未知码回退为可读句子而不泄漏裸标识符；调用方为 `MigrationWizardSteps.tsx`（向导预览）与 `MemoryImportReviewDialog.tsx`（导入审阅弹窗） |
