# Interactive Styled Spreadsheet Viewer & Multi-Office Sync Hub

## 架构定位

高颜值出版级电子表格渲染引擎、自动主题排版与多办公生态双向同步管道（Interactive Styled Spreadsheet Viewer & Multi-Office Sync Hub · Item 19）为工作区提供专业级数据表格看板。彻底消除传统 AI 导出裸 CSV / 粗糙 Markdown 表格的痛点，支持四大出版级商务主题（商务深蓝、现代黑金、财务经典绿、科技石板灰）实时切换、模糊搜索、列排序、一键导出美化 Excel 与一键分发同步至飞书多维表格（Bitable）、企业微信文档与钉钉表格。

## 模块清单

| 文件 | 职责 | 行数/规范 |
|---|---|---|
| `InteractiveSpreadsheetViewer.tsx` | 现代高颜值电子表格交互看板：支持四大主题切换、表头排序、实时模糊过滤、数值靠右对齐、一键导出美化 Excel 与一键多办公分发 | `< 320` 行，零 `any`，Tailwind 响应式 |
| `MultiOfficeSyncModal.tsx` | 多办公协同生态一键分发对话框：语义化 `<dialog>`，支持目标平台切换（飞书/企微/钉钉）、表名编辑、字段/记录总数统计、同步执行与直达外链分享 | `< 200` 行，零 `any`，零原生 emoji |
| `index.ts` | 门面导出文件：统一导出交互式看板与多办公分发对话框 | 统一入口 |
| `_ARCH.md` | 本模块架构说明与文件职责索引 | 遵循架构规范 |

## 核心特性

1. **四大出版级商务主题切换**：支持商务深蓝（`business_navy`）、现代黑金（`dark_gold`）、财务翡翠绿（`financial_emerald`）与科技石板灰（`tech_slate`）动态切换，与后端 Excel 渲染引擎 1:1 视觉契约对齐；
2. **现代交互能力**：支持全局模糊搜索关键词高亮过滤、单列点击排序（升序/降序）、数值/百分比/货币自动右对齐；
3. **多办公协同生态互通**：支持将格式化表格数据一键分发到飞书多维表格、企业微信文档或钉钉表格；
4. **全端消除 Dead Feature Path**：在 `LocalizedProviders.tsx` 全局挂载，支持通过全局事件 `myrm:open-spreadsheet-viewer` 或受控属性一键呼出。
