# Auxiliary Workbench Component Architecture

## 1. 概述与定位

本模块位于 `myrm-agent-frontend/src/components/features/workbench/`，对标 Roadmap Item 25 (`IndependentMultiTabAuxiliaryWorkbenchWithBuiltinDiffAndPty` · P0)。
彻底打破传统单对话框孤岛限制，为开发者和重型任务用户提供 IDE 级别的多面板辅助工作台协同：

1. **右侧/底部双轴独立停靠抽屉 (`MultiTabWorkbench`)**：支持水平调宽（320px ~ 960px）与垂直调高（200px ~ 640px），双轴灵活停靠；
2. **跨磁盘工作区文件管理器 (`tabs/WorkbenchFileExplorer`)**：目录树递归展开、文件模糊搜索与代码即时语法高亮预览；
3. **行内与分栏代码 Diff 对比器 (`tabs/WorkbenchDiffViewer`)**：Before/After 差异对比、增删行号高亮、统一 diff 复制与变更回滚；
4. **宿主机真实 PTY 终端面板 (`tabs/WorkbenchTerminal`)**：终端历史执行记录、ANSI 格式化、命令执行与一键将终端日志插入聊天会话上下文；
5. **GitHub 插件生命周期与健康中心 (`tabs/WorkbenchPluginCenter`)**：插件列表、探活状态检查与自动修复；
6. **工具菜单入口 (`WorkbenchToggleTrigger`)**：导航栏「工具」菜单唤起，保留快捷键 `Cmd+Shift+B` / `Ctrl+Shift+B` 与全局事件 `myrm:open-workbench`；`showTrigger={false}` 时只保留监听。

## 2. 模块结构与文件表

| 文件                             | 职责                                                                    |
| -------------------------------- | ----------------------------------------------------------------------- |
| `MultiTabWorkbench.tsx`          | 工作台主外壳容器，包含 Tab 切换、拖拽手柄尺寸调节、停靠位置转换与无障碍 |
| `WorkbenchToggleTrigger.tsx`     | 工具菜单入口与全局快捷键调度器（`showTrigger` 控制是否渲染入口）        |
| `tabs/WorkbenchFileExplorer.tsx` | 工作区文件树检索与代码预览面板                                          |
| `tabs/WorkbenchDiffViewer.tsx`   | 行内/分栏代码 Diff 对比与差异分析面板                                   |
| `tabs/WorkbenchTerminal.tsx`     | PTY 终端控制台、命令执行与会话注入面板                                  |
| `tabs/WorkbenchPluginCenter.tsx` | GitHub 插件生命周期与健康探针中心                                       |
| `index.ts`                       | 门面导出入口                                                            |
| `__tests__/`                     | 组件单元测试套件                                                        |

## 3. 设计红线与质量约束

- **零 any**：所有状态和组件属性必须使用具体 Type Hints；
- **行数控制**：单文件严格控制在 350 行以内，单一职责；
- **零原生 emoji**：图标全量使用标准 SVG 矢量组件；
- **无障碍访问**：满足 `role="complementary"`, `role="tab"`, `role="separator"`, `aria-label` 等 a11y 规范。
