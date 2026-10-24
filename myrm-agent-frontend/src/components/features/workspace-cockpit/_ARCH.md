# Workspace Cockpit Module

个人数字员工工作区总控驾驶舱、4 泳道全局任务流与“你不在的时候”离线概览模块。
提供个人 Agent 工作区控制台与管家全局总览，并为每条后台任务内嵌实时输出流最新一行（Streaming Tail）。

## 文件组织

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `workspaceCockpitTypes.ts` | Types | 4 泳道分类、任务项数据模型、离线摘要统计契约定义 | [INPUT] 无外部运行时依赖<br>[OUTPUT] 导出数据类型与泳道枚举<br>[POS] 驾驶舱数据模型事实源 |
| `useWorkspaceOfflineDigest.ts` | Hook | 用户活跃时间感知、离线时长计算与离线成果/风险统计计算引擎 | [INPUT] workspaceCockpitTypes<br>[OUTPUT] 离线摘要指标与计算状态<br>[POS] 离线活跃态计算逻辑 |
| `WhileYouWereAwayDigest.tsx` | UI | “你不在的时候”离线成果横幅卡片，含 4 维指标徽标与关键变更 Highlights | [INPUT] workspaceCockpitTypes, useWorkspaceOfflineDigest<br>[OUTPUT] 离线成果卡片组件<br>[POS] 离线成果展示界面 |
| `GlobalFourSwimlanesDeck.tsx` | UI | 4 泳道全局任务流驾驶舱（Needs You、In Progress、Observing、Scheduled），内嵌实时 streaming tail 与一键审批 | [INPUT] workspaceCockpitTypes<br>[OUTPUT] 4 泳道任务流列表组件<br>[POS] 多泳道任务状态大盘 |
| `ManagerConversationTray.tsx` | UI | 右下角常驻悬浮/滑出轻量会话托盘，支持快速微调与全局问答 | [INPUT] workspaceCockpitTypes<br>[OUTPUT] 管家悬浮抽屉交互卡片<br>[POS] 常驻管家问答入口 |
| `WorkspaceManagerCockpit.tsx` | Core | 顶层管家工作台主表面，整合搜索、刷新、离线摘要与 4 泳道网格 | [INPUT] 内部所有子组件<br>[OUTPUT] 工作区驾驶舱主界面<br>[POS] 顶层聚合主工作台 |
| `index.ts` | Facade | 统一门面导出 | [INPUT] 模块内部所有导出<br>[OUTPUT] 统一向外部提供公共 API<br>[POS] 模块对外唯一门面 |

## 外部依赖

- `@/lib/utils/classnameUtils` (Tailwind CSS 类名组合)
- `lucide-react` (统一轻量级矢量图标)

## 生产集成点

- 挂载至 WebUI 工作区主视图与 Tauri 桌面端原生总控面板
- 支持按任务与会话 ID 一键穿透导航至主聊天或调试节点
