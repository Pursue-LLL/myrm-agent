# artifacts/ 模块架构

---

## 架构概述

聊天流工件展示与一键部署 UI。卡片/预览双入口，hydrate 部署状态，过期版本提示重新部署。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `ArtifactCard.tsx` | 核心 | 聊天流卡片；hydrate；Globe 部署；`isDeploymentStale` redeploy banner（移动/桌面响应式） |
| `ArtifactPreview.tsx` | 核心 | 全屏预览；同款 redeploy banner |
| `DeployModal.tsx` | 核心 | Vercel BYOK / 平台 Token 部署弹窗 |
| `artifactUtils.ts` | 辅助 | `isDeploymentStale`、`patchArtifactDeploymentInChat`、图标与格式化 |
| `ArtifactRenderer.tsx` | 核心 | 多类型工件渲染路由 |
| `renderers/MediaPreview.tsx` | 辅助 | `HtmlPreview` 沙箱 iframe（主题桥、自动高度） |

---

## 依赖关系

- `@/lib/api`：artifact GET、deploy POST/WS
- `@/store/chat`：部署字段同步
- `app/api/files/deploy_api.py`（服务端）
