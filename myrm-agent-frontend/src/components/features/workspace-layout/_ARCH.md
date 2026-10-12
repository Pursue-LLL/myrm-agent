# Four Preset Workspace Layout Switcher

## 架构定位

四大预置工作区布局切换器（Four Preset Workspace Layout Switcher）为适应不同开发场景和视口重心的全站布局管理子系统。提供「代码副驾模式 (Copilot)」、「多 Agent 矩阵模式 (Multi-Agent Cluster)」、「云端算力监控模式 (Remote Compute)」与「精简日常模式 (Easy Minimal)」一键平滑切换，持久化用户偏好至 LocalStorage，消除复杂多面板手动拖拽与配置摩擦。

## 模块清单

| 文件 | 职责 | 行数/规范 |
|---|---|---|
| `PresetWorkspaceGrid.tsx` | 4 种预置布局的网格与分栏自适应容器（代码审查 Diff 侧栏、多任务集群拓扑、算力遥测栏与居中单栏） | `< 160` 行，零 `any`，Tailwind 响应式 |
| `LayoutModeChoiceModal.tsx` | 布局选择模态框：语义化 `<dialog>`，4 种预置卡片点选、高亮激活徽章与偏好应用 | `< 220` 行，零原生 emoji |
| `WorkspaceLayoutBar.tsx` | 常驻 HUD 布局切换条：展示当前布局标签与图标，监听 `Cmd+Shift+L` / `Ctrl+Shift+L`，消除 Dead Feature Path | `< 110` 行，遵循设计系统 |
| `index.ts` | 门面导出文件：统一导出容器、选择框与状态条 | 统一入口 |
| `_ARCH.md` | 本模块架构说明与文件职责索引 | 遵循架构规范 |

## 模式特性索引

1. **Copilot（代码副驾）**：强化 AST/Diff 树与终端执行日志；
2. **Multi-Agent（多 Agent 矩阵）**：多列网格并排监控并发任务；
3. **Remote Compute（云端算力）**：侧重远端 GPU/沙箱/网络传输水位；
4. **Easy Minimal（精简日常）**：居中单栏大输入框，极简沉浸式对话。
