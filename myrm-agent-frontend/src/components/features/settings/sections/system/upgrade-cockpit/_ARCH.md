# upgrade-cockpit/

## 架构概述

本模块实现 WebUI 与桌面端可视化一键无感升级控制台、多源网络诊断探针与长任务排队热重载面板（GuiOneClickInAppUpgradeAndPreFlightDiagnosticCockpit）。
彻底告别非技术用户使用智能体时被迫进入黑盒命令行终端敲 `update` 指令、面对一片死寂与跨境端口超时束手无策、以及盲目更新强杀后台运行任务的恶劣体验。
覆盖 WebUI/Tauri 内置一键检查更新、图形化前置网络体检探针（实时探测 GitHub/CNB/清华/Gitee 延迟与丢包）、运行中长任务防误杀智能排队（自动识别活动 Goal/Cron 并在安全轮次热重载）、五阶段原子流水线、双实例冷热接力（Blue-Green Standby）以及一键秒级无损回滚快照保护。对标 Hermes CLI update 痛点并彻底升维至 GUI-first 顶尖生产体验。

## 文件组织

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `upgradeCockpitTypes.ts` | Types | 核心数据模型契约（NetworkMirrorProbeResult, ActiveTaskDrainSafetyCheck, UpgradeStage, UpgradeStageStep, RollbackSnapshotMetadata） | [INPUT] 无外部运行时依赖<br>[OUTPUT] 导出网络体检、安全排空与升级流水线数据契约<br>[POS] 升级控制台类型事实源 |
| `useUpgradePreFlightDiagnostics.ts` | Hook | 前置网络多源体检、活动长任务安全排空探测与五阶段升级流水线状态机 | [INPUT] upgradeCockpitTypes<br>[OUTPUT] 镜像探针、活动任务告警、流水线流转与秒级回滚控制器<br>[POS] 一键无感升级核心业务逻辑与状态机 |
| `UpgradePreFlightProbeCard.tsx` | UI | 多源网络前置体检大盘组件（展示延迟、健康度与一键切换镜像通道） | [INPUT] NetworkMirrorProbeResult 数组与切换回调<br>[OUTPUT] 响应式多源网络健康度可视化卡片<br>[POS] 升级前置网络体检交互视图 |
| `ActiveTaskDrainSafetyBanner.tsx` | UI | 活动长任务防误杀安全建议横幅（长任务拦截与自动重载/快照决策） | [INPUT] ActiveTaskDrainSafetyCheck 与策略选择回调<br>[OUTPUT] 安全排空或保存快照决策横幅<br>[POS] 升级前长任务防误杀防护横幅 |
| `DualInstanceHandoffPipelineModal.tsx` | Core | 五阶段原子升级流水线、双实例无感接力与一键秒级回滚模态框 | [INPUT] UpgradeStageStep 进度状态与回滚回调<br>[OUTPUT] 全程可视化步进卡片、双实例接力动画与完成高光卡片<br>[POS] 升级流水线总控主模态界面 |
| `index.ts` | Facade | 门面统一导出 | [INPUT] 模块内部所有导出<br>[OUTPUT] 统一向外部提供公共 API<br>[POS] 模块对外唯一门面 |

## 外部依赖

- `lucide-react` (Globe, Zap, RotateCw, AlertTriangle, ShieldCheck, RefreshCw, Undo2 等统一轻量矢量图标)
- `@/lib/utils/classnameUtils` (Tailwind 类名合并)

## 生产集成点

- 挂载至系统设置/关于更新面板（`StackUpdatePanel.tsx` / `AboutSection.tsx`）
- 在 Local WebUI 与 Tauri 桌面端提供统一的一键可视化无感更新通道
