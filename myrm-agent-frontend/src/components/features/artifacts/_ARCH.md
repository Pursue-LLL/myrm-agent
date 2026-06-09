# artifacts/ 模块架构

---

## 架构概述

聊天流工件展示：Vercel 部署、部署 preflight 门禁、只读分享短链（服务端物化与 deploy 同规则的多文件静态包 + HMAC 公网查看）、知识库写入、对话附件插入。卡片与全屏预览双入口一致。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `ArtifactCard.tsx` | 核心 | 聊天卡片；Link 只读分享；Globe 部署（preflight 通过才可部署）；BookOpen 写入 Wiki 知识库；MessageSquarePlus 插入当前对话 |
| `ArtifactPreview.tsx` | 核心 | 全屏预览；与卡片相同的分享/部署入口（`flex-wrap` 响应式） |
| `DeployModal.tsx` | 核心 | Vercel 部署；打开时拉取 preflight |
| `artifactUtils.ts` | 辅助 | preflight/share API 客户端、`isDeploymentStale`、图标 |
| `ArtifactRenderer.tsx` | 核心 | 多类型工件渲染路由（code/document/html/pdf/svg/mermaid/image/video/audio/spreadsheet） |
| `renderers/MediaPreview.tsx` | 辅助 | `HtmlPreview` 沙箱 iframe（主题桥、自动高度） |
| `renderers/SpreadsheetPreview/` | 辅助 | CSV/TSV/XLSX 交互式表格预览 |
| `renderers/SpreadsheetPreview/CsvParser.ts` | 辅助 | RFC 4180 合规 CSV/TSV 解析器，自动检测分隔符 |
| `renderers/SpreadsheetPreview/DataGrid.tsx` | 辅助 | 虚拟滚动表格（排序/搜索/复制/导出） |
| `renderers/SpreadsheetPreview/index.tsx` | 辅助 | 路由器：CSV/TSV 直接解析，XLSX 动态导入 SheetJS + 多 Sheet 切换 |

---

## 依赖关系

- `@/lib/api`：artifact GET、deploy POST/WS
- `@/store/chat`：部署字段同步、`setFiles()` 插入对话附件
- `@/services/wikiService`：`ingestArtifact()` Wiki 知识库写入
- `@tanstack/react-virtual`：DataGrid 虚拟滚动
- `xlsx`（动态导入）：XLSX/XLS 文件解析
- `app/api/files/deploy_api.py`、`artifact_share_api.py`（服务端）
- `app/api/wiki/router.py`：`POST /wiki/ingest`（服务端）
