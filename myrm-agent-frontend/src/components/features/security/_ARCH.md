# features/security/

## 架构概述

安全防线与敏感出网人眼审批（HITL）交互组件。呈现网络拦截、凭证保护和会话级信任控制。

## 文件清单

| 文件 | 职责 |
| --- | --- |
| `TaintedEgressApprovalModal.tsx` | 敏感数据出网人眼拦截审批模态框（纯 Lucide 图标、双主题、会话防疲劳信任） |

## 依赖

- `lucide-react` — 矢量图标
- `next-intl` — 国际化字典 (`security.taintedEgress`)
