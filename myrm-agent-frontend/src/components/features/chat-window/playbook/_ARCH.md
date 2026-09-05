# playbook/

## 架构概述

模型编排最佳实践领域子包：包含模型编排心智科普、三大黄金编排预设（Recipe Engine）、就绪度匹配算法以及一键增量写入配置流。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `index.ts` | 门面 | 聚合导出 Playbook 弹窗、发现胶囊、预设模型与配置应用函数 | ✅ |
| `ModelOrchestrationPlaybookChip.tsx` | 组件 | EmptyChat 首屏轻量发现胶囊，支持 sessionStorage 免扰关闭并唤起主看板 | ✅ |
| `ModelOrchestrationPlaybookDialog.tsx` | 组件 | 交互式模型编排看板弹窗（四象限图解、三大预设卡片、Token 经济学与一键套用） | ✅ |
| `modelOrchestrationRecipes.ts` | 核心 | 三大黄金编排预设常量、已启用模型智能匹配解析器与原子增量 Patch 写入引擎 | ✅ |
| `__tests__/ModelOrchestrationPlaybook.test.tsx` | 测试 | 编排预设匹配、就绪度解析与组件渲染交互全流程单元测试 | ✅ |
| `__tests__/ModelOrchestrationPlaybookDialog.test.tsx` | 测试 | 编排看板弹窗渲染、预设切换与一键套用交互单元测试 | ✅ |
| `__tests__/modelOrchestrationRecipes.test.ts` | 测试 | 模型就绪度智能匹配、候选匹配与配置增量 Patch 算法单测 | ✅ |

## 模块依赖

- 消费 `@/store/useProviderStore` 进行模型服务商与默认模型配置的原子化读取与增量更新；
- 遵循 `tailwind.config.ts` 双主题调色板与 Lucide 矢量科技图标标准；
- 通过 `locales/*.json` 中的 `chat.modelPlaybook` 实现 6 语系国际化支持。
