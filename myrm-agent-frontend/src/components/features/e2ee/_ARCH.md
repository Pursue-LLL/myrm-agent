# e2ee/

## 架构概述

E2EE 安全状态 UI 组件。可复用于所有需要展示端到端加密状态的页面。

## 文件清单

| 文件 | 职责 |
|------|------|
| `E2EESecurityPanel.tsx` | 可复用 badge + Popover：成功态显示绿色 ShieldCheck + 安全详情（算法/指纹/会话ID），失败态显示红色 ShieldX 错误提示 |

## 依赖

- `@/lib/e2ee/useE2EEStatus` — E2EE 状态数据源
- `@/components/primitives/popover` — Radix Popover
- `lucide-react` — ShieldCheck / ShieldX 图标
- `next-intl` — i18n (`e2ee` 命名空间)
