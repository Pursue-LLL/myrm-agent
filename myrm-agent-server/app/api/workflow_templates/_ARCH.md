# workflow_templates API

## 架构概述

HTTP boundary for the Dynamic Workflow named template library (vMIN).

## 文件清单

| 文件 | 职责 | I/O/P |
| --- | --- | --- |
| `router.py` | REST CRUD + save-from-run; GET detail includes `bound_cron_count`; PUT upsert is import SSOT for Web UI JSON bundle | ✅ |
| `__init__.py` | Router re-export | — |

## 模块依赖

- `app.services.workflow_templates.service` — harness `WorkflowTemplateStore` wrapper
- `app.schemas.workflow_templates` — request/response DTOs

## E2E

- `tests/e2e/test_workflow_template_save_rerun_chrome_e2e.py` — save-from-run → pinned rerun
- `tests/e2e/test_workflow_template_export_import_chrome_e2e.py` — GET bundle → delete → UI import roundtrip
