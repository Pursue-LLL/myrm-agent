# interactive-ui/

## 架构概述

Agent 在对话内渲染的声明式 UI（`UI_UPDATE` SSE → `uiArtifacts` → 组件树）。用户操作通过 i18n 用户消息回传 Agent；`<ui_action_data>` 仅 Agent 可见，聊天气泡由 `stripUserMessageDisplayText` 过滤。

## 文件清单

| 文件                           | 地位 | 职责                                                                                                                                                          | I/O/P |
| ------------------------------ | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `InteractiveUIDisplay.tsx`     | 组件 | 多 surface 容器；artifact.title 为唯一用户可见标题                                                                                                            | ✅    |
| `InteractiveUIRenderer.tsx`    | 组件 | 递归渲染组件树（`.interactive-ui-container`）；渲染时统一将 `bindings`（prop 名 → 数据路径）从数据模型解析并覆盖 props，所有展示/表单组件自动获得数据驱动能力 | ✅    |
| `UIComponentRegistry.tsx`      | 核心 | 组件 type → React 映射注册表                                                                                                                                  | ✅    |
| `UIComponentErrorBoundary.tsx` | 组件 | 单组件 fail-closed 错误边界                                                                                                                                   | ✅    |
| `utils.ts`                     | 辅助 | `formatUIActionAsMessage`（Agent 载荷 + 用户可读正文）；`getValueByPath`/`setValueByPath`/`resolveBindings`（A2UI 数据绑定解析）                              | ✅    |
| `components/UIChart.tsx`       | 组件 | 图表渲染（bar/line/pie/donut）；原生 SVG 绘制，百分比坐标                                                                                                     | ✅    |
| `components/UITable.tsx`       | 组件 | 表格展示；`selectable` + `bindings.selected` 支持行勾选                                                                                                       | ✅    |
| `components/UIList.tsx`        | 组件 | 列表展示；`bindings.data` 绑定 `{title,subtitle?,description?}[]`                                                                                             | ✅    |
| `components/UIButtonGroup.tsx` | 组件 | 按钮组；single/multiple 选择模式                                                                                                                              | ✅    |
| `components/UITabs.tsx`        | 组件 | 标签页切换容器                                                                                                                                                | ✅    |
| `components/UIButton.tsx`      | 组件 | 单按钮；触发 `onAction` 事件                                                                                                                                  | ✅    |
| `components/UIContainer.tsx`   | 组件 | 布局容器（flex/grid/stack）                                                                                                                                   | ✅    |
| `components/UIText.tsx`        | 组件 | 文本展示（heading/body/caption）                                                                                                                              | ✅    |
| `components/UITextField.tsx`   | 组件 | 文本输入框                                                                                                                                                    | ✅    |
| `components/UITextarea.tsx`    | 组件 | 多行文本输入                                                                                                                                                  | ✅    |
| `components/UISelect.tsx`      | 组件 | 下拉选择器                                                                                                                                                    | ✅    |
| `components/UICheckbox.tsx`    | 组件 | 复选框                                                                                                                                                        | ✅    |
| `components/UIRadio.tsx`       | 组件 | 单选按钮组                                                                                                                                                    | ✅    |
| `components/UISwitch.tsx`      | 组件 | 开关切换                                                                                                                                                      | ✅    |
| `components/UISlider.tsx`      | 组件 | 滑块输入                                                                                                                                                      | ✅    |
| `components/UIDatePicker.tsx`  | 组件 | 日期选择器                                                                                                                                                    | ✅    |
| `components/UITimePicker.tsx`  | 组件 | 时间选择器                                                                                                                                                    | ✅    |
| `components/UIProgress.tsx`    | 组件 | 进度条                                                                                                                                                        | ✅    |
| `components/UIBadge.tsx`       | 组件 | 徽章/标签                                                                                                                                                     | ✅    |
| `components/UIImage.tsx`       | 组件 | 图片展示                                                                                                                                                      | ✅    |
| `components/UICard.tsx`        | 组件 | 卡片容器                                                                                                                                                      | ✅    |
| `components/UIGrid.tsx`        | 组件 | 网格布局                                                                                                                                                      | ✅    |
| `components/UIDivider.tsx`     | 组件 | 分割线                                                                                                                                                        | ✅    |
| `__tests__/`                   | 测试 | 组件与 `formatUIActionAsMessage` 回归                                                                                                                         | ✅    |

## 依赖

- `@/store/chat/types` — `UIArtifact`、`UIActionEvent`
- `@/lib/utils/messageUtils` — 展示层剥离 `ui_action_data`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
