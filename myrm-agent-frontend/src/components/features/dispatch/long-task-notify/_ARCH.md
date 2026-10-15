# FragmentTimeLongTaskDispatchCompletionNotifyAndRejoinSuite 架构设计

## 1. 核心定位
本套件聚焦通勤、地铁、午休等碎片时间场景，彻底解决长任务等待耗时问题。通过“发完走人（Fire-and-Forget）”模式，依托常驻云端/Server沙箱运行，移动瘦客户端切后台或锁屏不中断，任务完成后通过 Web Push/系统通知触达，并支持零闪烁增量断点重连与带来源权威清单就地复盘。

## 2. 模块分层
- `longTaskNotifyTypes.ts`: 长任务派发凭证、无人值守运行状态机、Web Push 通知渠道与带来源核验清单契约；
- `longTaskRejoinEngine.ts`: 纯算法层，支持时序格式化、动态 ETA 与剩余倒计时计算、断点重连差量补齐检测及推送负载生成；
- `useLongTaskNotifyStore.ts`: Zustand 状态管理中心，管控后台任务生命周期、切后台状态、通知权限、重连同步及全局派发事件；
- `FireAndForgetDispatchBar.tsx`: 一键长任务派发确认卡，支持耗时预估、通知偏好勾选与云端常驻免守候派发；
- `UnattendedRejoinStatusHUD.tsx`: 无人值守长任务悬浮态条，展示实时动态步进、进度条、后台保活指示与一键断点重连；
- `SourcedResultChecklistModal.tsx`: 完成后权威清单复盘弹窗，提供带官方权威源链接核验、一键复制与结果导入。
