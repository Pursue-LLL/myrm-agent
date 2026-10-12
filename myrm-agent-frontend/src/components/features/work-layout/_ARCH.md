# Work Layout Feature Module Architecture (`_ARCH.md`)

## 1. 模块定位与职责 (Item 26 · P0)
本子包位于 `src/components/features/work-layout/`，实现“对话 ↔ 工作”双模式流式布局与 Turbo/Pro 算力档位选择器 (`DualModeChatWorkLayoutAndTurboProComputeSelector`)。
打破轻量即时问答与重型长程任务混杂在单一宽度聊天流中的限制：
- **Chat Mode (极简对话模式)**：轻量单列居中，快速流畅响应；
- **Work Mode (全景工作台模式)**：展开四维资产侧边栏（Tasks 任务拆解、Skills 技能库、Connectors 外部连接器、Partners 协同伙伴），提供高密度工作全景视角；
- **Turbo vs Pro 算力与推理档位切换**：输入框/顶栏一键切换日常问答（Turbo）与深度长程推理（Pro）策略。

## 2. 核心组件拓扑与契约
| 组件 / 模块 | 职责与能力 | 契约 & 依赖 |
| :--- | :--- | :--- |
| `useWorkLayoutStore.ts` | 状态总线：管理 `viewMode`、`computeTier`、`workSidebarTab`、`tasks` 清单与进度 | Zustand，无 `any` |
| `ModeSwitchBar.tsx` | 对话 ↔ 工作 模式切换滑块，支持全局快捷键 `Mod+Shift+M` | Lucide SVG，无原生 emoji |
| `TurboProTierSelector.tsx` | Turbo (极速) ↔ Pro (深度推理) 算力档位切换微组件，支持单选与 Dropdown | 派发 `myrm:compute-tier-changed` 事件 |
| `WorkAssetSidebar.tsx` | 工作模式专属四维资产侧栏（Tasks, Skills, Connectors, Partners） | 包含任务勾选、进度条、技能调用与连接探活 |
| `DualModeContainer.tsx` | 响应式工作台外壳容器，按当前模式自适应分栏或单列 | 包含顶部指示栏与双模态切换控制 |
| `index.ts` | 子包公共门面导出 | 统一向宿主暴露核心组件 |

## 3. 设计原则与红线
1. **单一职责与行数红线**：每个组件严格小于 400 行，零冗余代码；
2. **类型安全**：严格使用 TypeScript Type Hints，严禁 `any` 类型；
3. **视觉与无障碍规范**：零原生 emoji，全部采用 Lucide 矢量图标，符合 `jsx-a11y` 交互规范；
4. **国际化支持**：中英双语（`namespaces/zh/workLayout.json` 与 `namespaces/en/workLayout.json`）。
