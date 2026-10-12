# templates 特性模块

## 架构概述

开箱即用行业级智能体应用模板中心与零提示词一键实例化工作台。覆盖 20+ 企业高频场景预置 Agent Persona 资产包、专属 Wiki 结构与内置 Workflow 蓝图一键克隆实例化。

上级文档：[../_ARCH.md](../_ARCH.md)。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `templateTypes.ts` | 核心 | 模板领域强类型定义（分类、成员、配置预览、Wiki蓝图、克隆选项与 Store 状态契约，零 any） | ✅ |
| `useTemplateMarketplaceStore.ts` | 核心 | 模板中心状态机（获取、检索过滤、分类切换、瞬时克隆事务与错误处理） | ✅ |
| `AgentTemplateCard.tsx` | 核心 | `<article>` 语义化模板卡片（分类/团队徽章、能力计数、场景 Pills 与克隆触发） | ✅ |
| `ZeroPromptCloneWorkbench.tsx` | 核心 | `<dialog>` 语义化零提示词瞬时实例化工作台模态框（人设/工具/Wiki蓝图预览、自定义命名与一键克隆） | ✅ |
| `AgentTemplateMarketplace.tsx` | 核心 | `<section>` 模板中心广场主容器（多行业分类 Tabs 筛选、搜索栏、卡片网格与空状态） | ✅ |
| `index.ts` | 门面 | 对外 re-export 公共组件与 Store | ✅ |

---

## 依赖关系

- 后端 API：`GET /api/v1/agents/templates`, `POST /api/v1/agents/instantiate-template/{id}`
- 图标库：`lucide-react`（全量矢量 SVG，零原生 emoji）
- 国际化：`templateMarketplace` 命名空间
- 状态库：`zustand`
