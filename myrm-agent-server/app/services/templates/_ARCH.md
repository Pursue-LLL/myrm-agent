# templates 模块

## 架构概述

企业级预置智能体应用模板中心服务与零提示词一键实例化引擎。负责发现、结构化解析 20+ 行业 Persona 资产包、专属沙箱 Wiki 结构蓝图以及原子化一键克隆实例化。

上级文档：[../_ARCH.md](../_ARCH.md)。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `agent_template_service.py` | 核心 | `AgentTemplateService` — 模板扫描、行业分类推断、专属 Wiki 蓝图映射与零提示词原子克隆 | ✅ |
| `__init__.py` | 门面 | 对外 re-export 公共 API (`AgentTemplateService`, `TemplatePreviewMeta`, `CloneTemplateOptions`) | ✅ |

---

## 依赖关系

- `assets/prebuilt_agents/*.yaml` — 预置模板资产包种子文件
- `app.services.agent.template_utils` — 国际化解析与预置技能启用检查
- `app.services.agent.agent_service` — Agent 创建与回滚事务
- `app.services.features.product_surface` — 隐藏模板过滤
