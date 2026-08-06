# workflow_templates service

## 架构概述

Thin server adapter over harness `WorkflowTemplateStore`. Shares `{harness_path}/.myrm/workflow_events.db` with the DW engine via `ContextAssemblyService.build_facade().harness_path()` SSOT.

## 文件清单

| 文件 | 职责 | I/O/P |
| --- | --- | --- |
| `service.py` | DB path resolution, record mapping (`placeholders` via harness SSOT) | ✅ |
| `validation.py` | Pinned/Cron bind guards + Cron execution-time template gate (harness SSOT) | ✅ |
| `__init__.py` | Package marker | — |

## 模块依赖

- `myrm_agent_harness.agent.dynamic_workflow.template_store::WorkflowTemplateStore`
