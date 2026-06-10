# settings/sections/system/

## 架构概述

系统 Tab：WebUI 配置、访问地址、浏览器池、内存监控、系统诊断等。`SystemSection` 为本地/WebUI 模式入口。

## 文件清单

| 文件 | 职责 |
|------|------|
| `SystemSection.tsx` | WebUI 开关、端口、访问地址（LAN 优先）；按 `useIngressRequirement` 条件展示 Tunnel / Public Ingress |
| `SystemCenterSection.tsx` | 系统 Tab 容器 |
| `BrowserPoolCard.tsx` / `LockedUseCard.tsx` / `WebuiAccessSecurityPanel.tsx` | 子功能卡片 |
| `DeveloperSection.tsx` / `DeveloperCenterSection.tsx` | 开发者工具 |
| `SecurityPolicySection.tsx` / `HeartbeatSection.tsx` | 安全与心跳 |

## 连通性 UX

- **LAN 优先**：内网 URL 默认展示，外网 Tunnel 折叠。
- **条件 Ingress**：`GET /api/v1/system/ingress-requirement` 返回 `required=true` 时展示 Quick Tunnel 与 Public Ingress；加载完成前不渲染公网区块（无闪烁）。
- 判定逻辑：Server `ingress_requirement.py` + 前端 `useIngressRequirement` 单 API。

## 依赖

- `@/hooks/useIngressRequirement`
- `@/hooks/useSystemConfig`、`@/hooks/useTunnel`
- `@/services/system`
