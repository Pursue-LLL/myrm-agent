# skeuomorphic-app/

## 架构概述

8 个源文件（3 个组件、1 个入口、2 个引擎、1 个类型、1 个状态仓库），6 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ClassicIpodTaskCarouselPlayer.tsx` | 组件 | 导出 `ClassicIpodTaskCarouselPlayer` | — |
| `PolaroidArtifactAlbumDeck.tsx` | 组件 | 导出 `PolaroidArtifactAlbumDeck` | — |
| `SkeuomorphicWorkbenchWidget.tsx` | 组件 | 导出 `SkeuomorphicWorkbenchWidget` | — |
| `index.ts` | 入口 | 聚合导出 `./skeuomorphicTypes`、`./skeuomorphicAudioEngine`、`./skeuomorphicAppEngine`、`./useSkeuomorphicAppStore`、`./ClassicIpodTaskCarouselPlayer`、`./PolaroidArtifactAlbumDeck`、`./SkeuomorphicWorkbenchWidget` | — |
| `skeuomorphicAppEngine.ts` | 引擎 | 导出 `calculateWheelAngle`、`calculateAngularStepDelta`、`wrapArtifactIndex`、`formatTaskDuration`、`formatTokenUsage`、`getDefaultMockArtifacts` | — |
| `skeuomorphicAudioEngine.ts` | 引擎 | 导出 `skeuomorphicAudioEngine` | — |
| `skeuomorphicTypes.ts` | 类型 | 导出类型 `SkeuomorphicSkinType`、`ArtifactCategory`、`TaskRunStatus`、`ArtifactPlayItem`、`WheelGestureState`、`SynthAudioConfig` 等 7 个 | — |
| `useSkeuomorphicAppStore.ts` | 状态仓库 | 导出 `useSkeuomorphicAppStore` | — |
| `__tests__/ClassicIpodTaskCarouselPlayer.test.tsx` | 测试 | `ClassicIpodTaskCarouselPlayer`；4 个用例 | — |
| `__tests__/PolaroidArtifactAlbumDeck.test.tsx` | 测试 | `PolaroidArtifactAlbumDeck`；3 个用例 | — |
| `__tests__/SkeuomorphicWorkbenchWidget.test.tsx` | 测试 | `SkeuomorphicWorkbenchWidget`；4 个用例 | — |
| `__tests__/skeuomorphicAppEngine.test.ts` | 测试 | `skeuomorphicAppEngine`；6 个用例 | — |
| `__tests__/skeuomorphicAudioEngine.test.ts` | 测试 | `skeuomorphicAudioEngine`；3 个用例 | — |
| `__tests__/useSkeuomorphicAppStore.test.ts` | 测试 | `useSkeuomorphicAppStore`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
