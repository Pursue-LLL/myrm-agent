# Compaction Milestone Feature Module Architecture (`_ARCH.md`)

## 1. 模块定位与职责 (Item 27 · P0)
本子包位于 `src/components/features/compaction-milestone/`，实现“记忆结晶压缩折叠卡片、分支经验流可视化导航与只读历史时光机” (`CompactedMilestoneCardAndBranchSummaryVisualizer`)。
彻底消除 Agent 长程任务中多次自动压缩造成的黑盒截断焦虑，以及分支切换后探索经验丢失的痛点：
- **CompactedMilestoneCard**：以流式胶囊折叠卡呈现 5 段式结构化记忆结晶摘要（目标、进展、核心决策、下一步、关键上下文与读写文件列表），直观展示节约 Token 仪表；
- **ReadOnlyTimeMachineDrawer**：只读历史时光机折叠抽屉，低饱和度淡雅背景展示原始消息快照，常驻「只读审计归档 · 不发给模型」水印与追溯信息；
- **BranchSummaryCard**：跨分支经验飞线指示器卡片，展示跨分支继承的认知与探索经验，提供一键穿梭回源分支能力。

## 2. 核心组件拓扑与契约
| 组件 / 模块 | 职责与能力 | 契约 & 依赖 |
| :--- | :--- | :--- |
| `compactionTypes.ts` | 定义 `CompactionEntry`、`BranchSummaryEntry`、`CompactedMessageSnapshot` 核心强类型契约 | 严格零 `any` |
| `compactionParser.ts` | 纯函数摘要解析器，将纯文本 Markdown 摘要与锚点元数据转换为 5 段式结构化 CompactionEntry | 零 `any`，单测 2/2 全绿 |
| `CompactedMilestoneCard.tsx` | 5 段式结构化摘要卡片，包含折叠胶囊、Token 统计仪表、内联时光机入口 | React 19，Lucide SVG |
| `ReadOnlyTimeMachineDrawer.tsx` | 原地展开只读历史时光机抽屉，展示原始被压缩消息快照与审计水印 | 语义化 `<section>`，只读视图 |
| `BranchSummaryCard.tsx` | 跨分支经验连线微卡片，展示源分支名、核心经验衍生点，支持穿梭回源分支 | 派发 `myrm:warp-to-branch` |
| `index.ts` | 子包公共门面导出 | 导出核心组件与数据模型 |

## 3. 设计原则与红线
1. **单一职责与行数红线**：每个组件单文件严格小于 300 行；
2. **类型安全**：零 `any`，强类型契约；
3. **视觉与可访问性**：零原生 emoji，全部采用 Lucide 矢量图标，满足 `jsx-a11y` 交互规范；
4. **国际化支持**：双语国际化（`namespaces/zh/compaction.json` 与 `namespaces/en/compaction.json`）。
