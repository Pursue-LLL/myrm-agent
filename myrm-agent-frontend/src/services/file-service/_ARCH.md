# services/file-service/ 模块架构

## 架构概述

**平台文件 I/O 抽象层**（选文件、读 DataURL、`StoreFile` 互转）。与同级 `../file.ts`（HTTP 上传与 PDF/文档解析 API）职责分离，勿混用导入路径。

| 模块 | 职责 |
|------|------|
| `file.ts`（上级） | `uploadFiles`、进度回调、`extractPdfContent` 等 **server API** |
| `file-service/`（本目录） | Tauri 本地 FS vs Sandbox HTTP 的 **FileService 策略** |

## 文件清单

| 文件 | 职责 |
|------|------|
| `index.ts` | `getFileService()` 单例；`selectFiles` / `readFileAsDataURL` 门面 |
| `types.ts` | `FileService`、`StoreFile`、`FileReference`；复用 `file.ts` 的 `UploadProgress` |
| `tauri.ts` | 桌面端原生对话框与 FS 读 |
| `sandbox.ts` | Web/Sandbox：委托 `file.ts` 上传 API |

## 依赖

- `@/lib/deploy-mode` — `isTauriRuntime()` 分支
- `@/services/file` — sandbox 上传与类型

## 约束

- 新消费者：选/读本地文件 → `file-service`；直传 server → `file.ts`
- 禁止新增 `file-service/index.ts` 以外的桶导出
