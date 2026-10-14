# services/memory/business_templates 模块架构

## 架构概述

零售售后换货与经营分析复盘的业务经验模板：领域模型、三套预置模板（经营分析复盘 `BA-REV-01`、售后换货规程 `RET-EXC-01`、例外转人工门禁 `ESC-GATE-01`）以及按订单上下文评估转人工边界的引擎。模板内容与门禁规则属于业务领域，只存放在 Server 业务层；harness 框架层不包含任何零售/订单语义。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出领域模型、预置模板与 `BusinessTemplateEngine` | ✅ |
| `models.py` | 类型 | 模板、检查清单步骤、转人工决策与评估上下文、验证记录等领域模型 | ✅ |
| `seed_templates.py` | 核心 | 三套预置业务经验模板（冷启动数据） | ✅ |
| `template_engine.py` | 核心 | 模板查询/检索、转人工边界评估、验证反馈计数演化 | ✅ |

## 模块依赖

- 上游：`pydantic`
- 下游：`app/services/memory/business_template_service.py`（应用服务与 DTO 映射）
