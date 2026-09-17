# theme-studio/hooks/

## 架构概述

Theme Studio 的网关与预览 hooks：市场可达性（CP 健康 + JWT）单次探测后由 Provider 共享，避免每个面板重复探测；DOM 预览只做本地编译，零 ConfigSync 写入。

## 文件清单

| 文件                                | 地位 | 职责                                                         | I/O/P |
| ----------------------------------- | ---- | ------------------------------------------------------------ | ----- |
| `ThemeMarketplaceGateProvider.tsx`  | 核心 | 共享 CP `/api/health` + JWT 网关（所有面板单次探测）          | ✅    |
| `useThemeMarketplaceGate.ts`        | 核心 | 网关 context hook 再导出                                     | ✅    |
| `useThemeStudioDomPreview.ts`       | 核心 | 工作区实时预览：仅 DOM 编译，零 ConfigSync 写入               | ✅    |

## 依赖

- `@/store/*`、`@/lib/api`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
