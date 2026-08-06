# workflow_templates API

## 架构概述

HTTP boundary for the Dynamic Workflow named template library (vMIN).

## 文件清单

| 文件 | 职责 | I/O/P |
| --- | --- | --- |
| `router.py` | REST CRUD + save-from-run | ✅ |
| `__init__.py` | Router re-export | — |

## 模块依赖

- `app.services.workflow_templates.service` — harness `WorkflowTemplateStore` wrapper
- `app.schemas.workflow_templates` — request/response DTOs
