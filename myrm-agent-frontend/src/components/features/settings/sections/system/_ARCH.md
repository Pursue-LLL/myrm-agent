# settings/sections/system/

## 架构概述

系统 Tab：WebUI 配置、访问地址、浏览器池、内存监控、系统诊断等。`SystemSection` 为本地/WebUI 模式入口。

## 文件清单

| 文件 | 职责 |
|------|------|
| `SystemSection.tsx` | WebUI 开关、端口、访问地址（LAN 优先）；公网 Ingress 粘贴 + 文档链接 |
| `SystemCenterSection.tsx` | 系统 Tab 容器 |
| `BrowserPoolCard.tsx` / `LockedUseCard.tsx` / `WebuiAccessSecurityPanel.tsx` | 子功能卡片 |
| `DeveloperSection.tsx` / `DeveloperCenterSection.tsx` | 开发者工具 |
| `SecurityPolicySection.tsx` / `HeartbeatSection.tsx` | 安全与心跳 |

## 连通性 UX

- **LAN 优先**：内网 URL 默认展示。
- **Public Ingress**：本地模式始终展示公网地址输入；用户自选穿透工具后粘贴（文档 `getDocsUrl('/guides/tunnel')`）。
- **条件引导**：`ingress-requirement` 的 `required` 控制引导文案（必须 vs 可选），不影响 Ingress 输入区可见性。
- 判定逻辑：Server `ingress_requirement.py` + 前端 `useIngressRequirement` 单 API。

## 依赖

- `@/hooks/useIngressRequirement`
- `@/hooks/useSystemConfig`
- `@/services/system`
- `@/lib/deploy-mode::getDocsUrl`
