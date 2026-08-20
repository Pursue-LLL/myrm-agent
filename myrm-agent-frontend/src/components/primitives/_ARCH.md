# primitives/

## 架构概述

shadcn/ui（New York）与 Radix 封装的纯展示/交互基元，无业务 API 调用。新增基元通过 `components.json` 的 `ui` 别名安装到本目录。

## 文件清单（节选）

| 文件                     | 地位 | 职责                                                     | I/O/P |
| ------------------------ | ---- | -------------------------------------------------------- | ----- |
| `button.tsx`             | 核心 | 按钮变体（default/destructive/outline/ghost/link）       | ✅    |
| `dialog.tsx`             | 核心 | Radix 模态对话框（Header/Footer/Content 组合）           | ✅    |
| `empty-state.tsx`        | 核心 | 标准化空状态/过渡态基元（带 PremiumIcons、CTA 与多变体） | ✅    |
| `skeleton.tsx`           | 核心 | 基础微光脉冲加载占位基元                                 | ✅    |
| `skeleton-templates.tsx` | 核心 | 常用拓扑骨架模板集（列表/卡片网格/表格/表单/主从双栏）   | ✅    |
| `sonner.tsx`             | 核心 | Sonner Toast 容器与主题适配                              | ✅    |
| `tooltip.tsx`            | 核心 | 悬浮提示（Provider + Content + Trigger）                 | ✅    |

完整列表见目录内 `*.tsx`（约 31 个基元文件）。

## 依赖

- `@/lib/utils/classnameUtils`（`cn`）
- Radix UI / `class-variance-authority`

## 被依赖

- `features/*` 各业务模块
- `features/app-shell/*` 全局壳组件
