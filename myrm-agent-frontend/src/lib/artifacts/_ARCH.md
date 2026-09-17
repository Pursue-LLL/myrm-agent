# lib/artifacts/

## 架构概述

产物行内批注的纯逻辑层：锚点哈希、模糊重定位、审阅消息组装与修订局域性校验。无 React 组件；状态见 `store/useArtifactAnnotationStore`，界面见 `components/features/artifacts/ArtifactAnnotationPanel`。

## 模块

| 文件                   | 职责                                                                                       |
| ---------------------- | ------------------------------------------------------------------------------------------ |
| `artifactAnnotations.ts` | 批注类型与锚点（djb2 哈希+摘录）、`relocateAnchor` 移位重定位、`composeReviewMessage` 组装、`verifyRevisionLocality` 越界校验 |
| `__tests__/`           | 上述纯函数的单测                                                                           |
