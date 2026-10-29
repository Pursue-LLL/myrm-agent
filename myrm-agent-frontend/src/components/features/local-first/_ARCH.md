# local-first/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），4 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `LocalFirstPrivacySandboxCard.tsx` | 组件 | 导出 `LocalFirstPrivacySandboxCard` | — |
| `WebGPUMetaArtifactViewer.tsx` | 组件 | 导出 `WebGPUMetaArtifactViewer` | — |
| `index.ts` | 入口 | 聚合导出 `./localFirstTypes`、`./localFirstPrivacyEngine`、`./useLocalFirstStore`、`./LocalFirstPrivacySandboxCard`、`./WebGPUMetaArtifactViewer` | — |
| `localFirstPrivacyEngine.ts` | 引擎 | 导出 `sanitizeClientSideData`、`convertJsonToFormat`、`calculateSimpleChecksum`、`buildRoamingRecord` | — |
| `localFirstTypes.ts` | 类型 | 导出类型 `StorageBackendType`、`TransformFormat`、`PrivacySanitizeResult`、`RoamingStateRecord`、`WebGPURenderMode`、`WebGPUArtifactSceneConfig` | — |
| `useLocalFirstStore.ts` | 状态仓库 | 导出 `useLocalFirstStore` | — |
| `__tests__/LocalFirstPrivacySandboxCard.test.tsx` | 测试 | `LocalFirstPrivacySandboxCard`；5 个用例 | — |
| `__tests__/WebGPUMetaArtifactViewer.test.tsx` | 测试 | `WebGPUMetaArtifactViewer`；4 个用例 | — |
| `__tests__/localFirstPrivacyEngine.test.ts` | 测试 | `localFirstPrivacyEngine`；11 个用例 | — |
| `__tests__/useLocalFirstStore.test.ts` | 测试 | `useLocalFirstStore`；7 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
