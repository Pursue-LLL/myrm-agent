# session-map/

## 架构概述

“项目维度可视化会话地图与 Agent 状态全景驾驶舱”前端交互矩阵：
对标 Mobius Agent OS 实践，提供宏观的 2D 拓扑会话地图（Session Map）与多 Agent 状态全景驾驶舱（Fleet Cockpit）。

- 项目容器强隔离：每个项目外包框强绑定独立的 Git 仓库、本地工作路径（`workspace_path`）与专属记忆/技能库；
- Agent 运行状态脉冲：SVG 2D 拓扑节点实时展示运行状态脉冲（`working` 绿波微动效、`ready` 蓝光常驻、`waiting_input` 琥珀金闪烁、`error` 绯红警示、`idle` 灰度暗光）；
- 全景驾驶舱 HUD：汇聚多 Agent 算力指标、活跃任务数量、即时搜索高亮与视图模式切换；
- 一键现场跳回看板：点击节点快速还原当时的任务上下文、Token 消耗与工作目录，一键跳转继续推进任务。

## 文件清单

| 文件                          | 职责                                                                                                                                  | 行数/规范                          |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| `SessionMapGraph.tsx`         | 2D 拓扑 SVG 画布组件：自动计算力导向/环形聚类坐标、渲染项目容器玻璃气泡、连线与 Agent 脉冲节点、缩放 HUD 控件                         | `< 350` 行，零 `any`，纯矢量 SVG   |
| `AgentFleetCockpit.tsx`       | 全景驾驶舱大盘指标卡条：全局项目/会话/状态分布、即时搜索输入框与模式切换                                                              | `< 250` 行，零 `any`，无原生 emoji |
| `SessionContextJumpModal.tsx` | 一键现场回溯模态框：语义化 `<dialog>`、展示目标会话详细信息与一键跳入操作                                                             | `< 220` 行，零 `any`，无原生 emoji |
| `SessionMapTrigger.tsx`       | 工具菜单入口与全屏模态看板装配层：监听全局快捷键 `Cmd+Shift+M` 与自定义事件，管理全景会话地图展开；`showTrigger={false}` 时只保留看板 | `< 320` 行，零 `any`               |
| `index.ts`                    | 门面导出文件：统一导出 `SessionMapGraph`、`AgentFleetCockpit`、`SessionContextJumpModal`、`SessionMapTrigger`                         | 统一入口                           |
| `_ARCH.md`                    | 本文档：模块架构说明与文件索引                                                                                                        | 符合架构规范                       |

## 数据流与交互闭环

1. **数据拉取**：挂载时调用 `fetchSessionMapProjects` 与 `fetchFleetCockpitSummary` 获取项目拓扑与大盘指标；
2. **交互缩放与检索**：用户可通过右上角缩放按钮或输入框即时高亮匹配的目标会话；
3. **现场回溯跳转**：点击目标节点呼出 `SessionContextJumpModal`，点击「跳入会话」触发全局 `myrm:open-chat-session` 事件导航。
