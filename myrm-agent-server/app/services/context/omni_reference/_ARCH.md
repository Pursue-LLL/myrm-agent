# omni_reference 模块

## 架构概述

全域多维上下文引用解析与切片服务。为前端输入框 `@` 补全提供跨文件、历史会话、工件、智能体、任务的 5 维实体聚合搜索与动态切片提取。

上级文档：[../_ARCH.md](../_ARCH.md)。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `service.py` | 核心 | `OmniReferenceResolverService` — 五维实体聚合搜索与动态切片提取，防上下文膨胀 | ✅ |
| `__init__.py` | 门面 | 对外 re-export 公共 API | ✅ |

---

## 依赖关系

- `myrm_agent_harness.agent.context_management.omni_reference` — 切片上限保护与 Prompt 注入格式化
