# artifacts/renderers/SpreadsheetEditor/

## 架构概述

Artifact Edit 模式下的 XLSX 交互编辑器：用 SheetJS 在 XLSX 与 Univer 数据模型之间双向转换，浏览器内编辑后导出保存，不依赖 Univer Pro 服务器。

## 文件清单

| 文件         | 地位 | 职责                                                               | I/O/P |
| ------------ | ---- | ------------------------------------------------------------------ | ----- |
| `index.tsx`  | 核心 | `SpreadsheetEditor`：Univer Sheet 引擎挂载、XLSX 双向转换与导出保存 | ✅    |

## 依赖

- `@univerjs/presets` + `@univerjs/preset-sheets-core`（POS: Sheet 编辑器引擎）
- `xlsx`（POS: SheetJS XLSX 读写）
- `@/lib/api` — `getStorageUrl` 工件 URL 拼接
- 父模块 [`../_ARCH.md`](../_ARCH.md)
