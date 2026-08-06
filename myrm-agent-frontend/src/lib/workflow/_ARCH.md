# lib/workflow/ 模块架构

## 架构概述

Dynamic Workflow 前端辅助：pinned 模板运行提交与模板 JSON 导入导出 bundle。

## 文件清单

| 文件 | 职责 | I/O/P |
| --- | --- | --- |
| `submitWorkflowTemplateRun.ts` | 从 Settings Library 或 armed bar 提交 pinned 模板 run | ✅ |
| `workflowTemplateBundle.ts` | v1 JSON bundle 构建、解析、浏览器下载 | ✅ |
| `useWorkflowTemplateTransfer.ts` | Library Export/Import 状态与 API 编排 hook | ✅ |
| `__tests__/workflowTemplateBundle.test.ts` | bundle 解析与文件名测试 | — |
| `__tests__/useWorkflowTemplateTransfer.test.ts` | Export/Import hook overwrite/throw 契约 | — |

Chrome E2E（server）：`tests/e2e/test_workflow_template_export_import_chrome_e2e.py` — Settings Import file picker roundtrip。

## 模块依赖

- `@/services/workflowTemplates` — REST client（GET detail、PUT upsert）
- `@/components/features/settings/sections/ai-tools/WorkflowTemplateLibrarySection.tsx` — 消费 transfer hook
