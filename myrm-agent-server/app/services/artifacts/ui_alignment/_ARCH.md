# services/artifacts/ui_alignment 模块架构

---

## 架构概述

多轮 UI 设计图视觉对齐与变体决策工作流服务（Item 39 P0）。
委托 Harness 引擎管理视觉 Mockup 变体对比池、画布交互批注列表，并在选定最优方案后固化为结构化 VisualContract（面向下游 Code Agent 提供强约束 Prompt）。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `service.py` | 核心 | `UiVisualAlignmentService` 单例服务，承载变体登记、画布批注采集、契约固化 |
| `__init__.py` | 门面 | 导出 `UiVisualAlignmentService` |
| `_ARCH.md` | 文档 | 模块架构描述与文件清单 |

---

## 依赖关系

- `myrm_agent_harness.toolkits.artifacts.ui_alignment`
