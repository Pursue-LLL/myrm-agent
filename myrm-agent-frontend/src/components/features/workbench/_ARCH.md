# Auxiliary Workbench Component Architecture

## 1. 概述与定位

本模块位于 `myrm-agent-frontend/src/components/features/workbench/`，为当前会话的工作区提供辅助工作台：

1. **右侧/底部双轴独立停靠抽屉 (`MultiTabWorkbench`)**：支持水平调宽（320px ~ 960px）与垂直调高（200px ~ 640px），双轴灵活停靠；没有当前会话时显示引导提示；切换会话时清空文件选中与终端历史；
2. **会话工作区文件管理器 (`tabs/WorkbenchFileExplorer`)**：目录树递归展开、文件模糊搜索与代码即时预览；二进制文件提示不可预览，大文件只显示开头并给出说明；
3. **会话工作区终端面板 (`tabs/WorkbenchTerminal`)**：在会话工作区内执行命令、终端历史记录、一键将终端日志插入聊天会话上下文；
4. **工具菜单入口 (`WorkbenchToggleTrigger`)**：导航栏「工具」菜单唤起，保留快捷键 `Cmd+Shift+B` / `Ctrl+Shift+B` 与全局事件 `myrm:open-workbench`；`showTrigger={false}` 时只保留监听。

## 2. 模块结构与文件表

| 文件                             | 职责                                                                    |
| -------------------------------- | ----------------------------------------------------------------------- |
| `MultiTabWorkbench.tsx`          | 工作台主外壳容器，包含 Tab 切换、拖拽手柄尺寸调节、停靠位置转换与无障碍 |
| `WorkbenchToggleTrigger.tsx`     | 工具菜单入口与全局快捷键调度器（`showTrigger` 控制是否渲染入口）        |
| `tabs/WorkbenchFileExplorer.tsx` | 会话工作区文件树检索与代码预览面板                                      |
| `tabs/WorkbenchTerminal.tsx`     | 会话工作区终端控制台、命令执行与会话注入面板                            |
| `index.ts`                       | 门面导出入口                                                            |
| `__tests__/`                     | 组件单元测试套件                                                        |

## 3. 设计红线与质量约束

- **异步回写守卫**：文件内容与命令输出的回写前，用 `useWorkbenchStore.sessionEpoch`（每次切换会话递增）与当前选中文件核对，上一个会话或被后点文件取代的迟到响应一律丢弃，不会串到新会话的界面；
- **零 any**：所有状态和组件属性必须使用具体 Type Hints；
- **行数控制**：单文件严格控制在 350 行以内，单一职责；
- **零原生 emoji**：图标全量使用标准 SVG 矢量组件；
- **无障碍访问**：满足 `role="complementary"`, `role="tab"`, `role="separator"`, `aria-label` 等 a11y 规范。
