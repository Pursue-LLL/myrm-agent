# artifacts/ 模块架构

---

## 架构概述

聊天流工件展示：Vercel 部署、部署 preflight 门禁、只读分享短链（服务端物化与 deploy 同规则的多文件静态包 + HMAC 公网查看）。卡片与全屏预览双入口一致。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `ArtifactCard.tsx` | 核心 | 聊天卡片；Link 只读分享；Globe 部署（preflight 通过才可部署） |
| `ArtifactPreview.tsx` | 核心 | 全屏预览；与卡片相同的分享/部署入口（`flex-wrap` 响应式） |
| `DeployModal.tsx` | 核心 | Vercel 部署；打开时拉取 preflight |
| `artifactUtils.ts` | 辅助 | preflight/share API 客户端、`isDeploymentStale`、图标 |
| `ArtifactRenderer.tsx` | 核心 | 多类型工件渲染路由 |
| `renderers/MediaPreview.tsx` | 辅助 | `HtmlPreview` 沙箱 iframe（主题桥、自动高度） |

---

## 依赖关系

- `@/lib/api`：artifact GET、deploy POST/WS
- `@/store/chat`：部署字段同步
- `app/api/files/deploy_api.py`、`artifact_share_api.py`（服务端）
