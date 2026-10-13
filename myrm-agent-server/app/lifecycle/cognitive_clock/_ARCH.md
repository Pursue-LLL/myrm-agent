# app/lifecycle/cognitive_clock 模块架构

嵌套多频认知时钟生命周期中枢。统一编排 T0-T3 四级认知自进化与维护节拍，集成前台打字活动感知与休眠唤醒平滑门禁。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 认知时钟模块公共符号导出与单例协调器获取入口 | ✅ |
| `coordinator.py` | 核心 | `CognitiveClockCoordinator`：四频嵌套主协调器，管理后台调度循环与唤醒心跳任务（同启同停）、自适应容量控制、打字让步与多频任务分发，门禁瞬时抑制时触发 15 分钟智能短退避重试并维护跳过遥测指标；每周一次的 T3 行为模式发现只在 T2 通过全部门禁（含预算）的节拍上执行，被拦截的节拍不消耗本周额度 | ✅ |
| `activity_sensor.py` | 核心 | `UserActivitySensor`：用户前台打字与交互活动感应器，30s 滑动窗口自动重置，驱动全局退避信号 | ✅ |
| `wakeup_guard.py` | 核心 | `WakeupSmoothingGuard`：笔记本休眠唤醒平滑防洪门禁，唤醒后延迟 180s 静默；唤醒由墙钟与单调时钟漂移（休眠时单调时钟暂停）或心跳漏拍（`run_heartbeat` 运行期间进程/主机被冻结）判定，没有心跳时只看漂移，两次读取之间的空闲间隔本身不算唤醒 | ✅ |
| `executors.py` | 辅助 | 分频维护执行器：T1 会话防抖提炼、T2 闲时维护流水线（清理/冲突自动解决/盲点收割/外部会话同步/健康快照/SQLite 热备份，任一步骤抛错则本轮 T2 不产出报告，T3 不随行）、T3 周期性行为模式发现 | ✅ |

## 模块依赖

- `myrm_agent_harness.runtime.cognitive_clock`：框架四频枚举与协作让步信号
- `myrm_agent_harness.runtime.maintenance`：容量准入与调度协议
- `app.services.memory`：记忆管理与账本审计
