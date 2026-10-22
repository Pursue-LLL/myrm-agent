# sandbox_wake/

## 架构概述

云托管沙箱的「到点唤醒」上报。空闲回收器会暂停沙箱容器，进程内定时器（目标额度窗口到点续跑、cron、看板改期任务到点解除）随之冻结；控制平面必须在这些时间点把沙箱唤醒，而它只能通过沙箱上报才知道时间。本包计算「下一次必须运行时间」并在变化时上报；唤醒后由进程自身的定时器接管。无控制平面配置（本地 / 自托管）时整包空转。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 门面 | 对外入口：`WakeScheduleReporter`、`get_wake_schedule_reporter` | ✅ |
| `next_wake.py` | ✅ 核心 | `earliest_scheduled_wake`：目标额度唤醒守护进程已 arm 的最早时间（`UsageLimitWakeDaemon.next_due_at`）、cron 下次运行（`CronStore.earliest_next_run`）与看板 `SCHEDULED` 改期任务的最早到点时间（`SqlAlchemyKanbanStore.earliest_scheduled_until`，查询以 `now` 为下界，逾期未处理的任务不会遮住之后的任务）取最小，仅计未来时间；提前 `_WAKE_LEAD_S`（60s，覆盖控制平面 30s 轮询粒度与 cron misfire 宽限）上报，距今不足提前量时按原时间上报 | ✅ |
| `reporter.py` | ✅ 核心 | `WakeScheduleReporter`：30s 轮询，值变化时或距上次成功上报满 10 分钟（心跳，恢复控制平面侧已放弃/丢失的触发）`PUT {CONTROL_PLANE_URL}/api/internal/sandboxes/{SANDBOX_ID}/wake-schedule`（telemetry token + `X-Sandbox-Id`）；失败不记已上报值，下一轮重试；上报成功后下次检查不晚于已上报时间本身（goal/cron 提前 60s 上报，到点后最早时间前移，控制平面会在发现沙箱已醒时清掉旧触发，必须趁空闲暂停冻结进程之前把新时间报上去；下限 2s 防空转）；`CONTROL_PLANE_URL` / token / `SANDBOX_ID` 任一缺失即不启动 | ✅ |

## 边界

- 只上报「时间」，不携带任何业务内容；控制平面侧存储与唤醒见 control-plane `orchestration/wake_scheduler.py`。
- 触发式 cron（event/system/webhook）没有 `next_run_at`，不上报；其入站流量本身经反向代理唤醒沙箱。
- 看板 `SCHEDULED` 改期任务（`scheduled_until`，含用户/agent 设定的定时解除、瞬时失败退避与额度窗口改期）计入上报；到点后由各看板调度器的进程内僵尸巡检（周期 `max(zombie_timeout/2, 30)` 秒）解除并派发，唤醒提前量 + 套餐最短闲置阈值（300s）足以覆盖一个巡检周期。
- 唤醒后的执行不经本包：目标由 `usage_limit_resume` 守护进程续跑，cron 由 `CronScheduler` 触发，看板任务由调度器派发；执行期间 `/api/v1/health/liveness` 报告 busy，回收器不会再暂停沙箱。

## 依赖

- `app.services.agent.goals.usage_limit_resume`（armed 目标时间）· `app.core.cron.adapters.setup`（cron store）· `app.services.kanban`（看板 store）· `app.config.settings`（`control_plane`）
