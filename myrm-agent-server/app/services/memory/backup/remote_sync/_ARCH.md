# services/memory/backup/remote_sync/

## 架构概述

记忆**远程（云端）备份**（WebDAV/S3）的全部：存储适配（`storage/`）、一次备份与远程恢复的运行器（`runner.py`），以及默认关闭的**定时备份**策略层——决定**何时备、每次结果怎么记、什么时候告知用户**。一次备份本身（快照 → 上传 → 轮转）由 `runner.run_remote_backup` 完成，手动「立即备份」与定时备份共用它，产物是同一种文件。

核心约束（代码为准）：

- **默认关闭**：`backupSync.enabled` 与 `backupSync.autoSync` 同时为真才会备份。设置读取自 Omni-Config 的 `backupSync`，本目录只读不写设置。
- **「到期」由记录的上次成功推导，不读远程列表**：读不到的远程与空文件夹无法区分，据此判断会把「连不上」当成「没有备份」。持久化的只有上次成功与上次尝试的时刻、最近错误码、连续失败数与「已告知」标记，存于 `{state_dir}/instance_archive/remote_memory_backup.json`。该目录在归档策略里是 RUNTIME 类（`policy.py`），实例备份不携带、导入不替换：恢复只改数据，不改计划已知的上传历史。内容损坏或被篡改时回落默认值（无时区的时刻按 UTC，计数钳到非负），代价是多备一次，不会崩溃。
- **间隔以用户所选为准**：调度器每 `TICK_MINUTES`（60 分钟）问一次「到期了吗」；用户所选 `syncInterval` 被钳到 60..1440 分钟（不是整数则取 1440）。判断留 5 分钟的抖动余量，否则恰在第 24 小时到期的备份要等到再下一个 tick。重启不会重复一个未到期的备份；启动 5 分钟后才首次检查，不与启动争抢。
- **只有成功推进计划**：失败记一次，下个 tick 重试，不看间隔。上次成功晚于当前时间（时钟拨快后又校正）不算「已备份」的证据，不会让备份停摆。
- **忙不是失败**：另一个备份（手动或上一轮）正在运行时，本轮什么都不做，也不记失败。
- **失败如实记录，不抛给调度器**：设置不可用（`config`）、快照不完整（`snapshot`）、上传失败（`upload`）、记忆存储打不开或其它未预料的异常（`internal`）各记一次失败并等待下个 tick；错误码是稳定的机器码，文案全部在前端 locale。
- **连续失败只告警一次**：第 2 次连续失败，且上次成功已超过两个间隔（或从未成功）时，发一次 `HEALTH_ALERT`（`component=remote_memory_backup`，数据带 `code`）；同一段连续失败里不再重复，成功即重置。Web Push 深链接与站内 toast 都指向 `/settings/memory?sub=cloud-backup`。告警在运行 tick 的事件循环上发出。
- **手动备份成功即结束失败期**：`record_manual_success` 把手动备份记作一次成功（连续失败与「已告知」清零，计划从此刻重新计时）；手动备份失败不开始新的失败期，用户正看着结果。
- **实例标记与整实例备份共用**：备份文件名里的实例标记取自 `AutoBackupStore.tag()`，一个实例只有一个标记，见 [`../../../instance_archive/auto_backup/_ARCH.md`](../../../instance_archive/auto_backup/_ARCH.md)；文件名与轮转规则见 [`../_ARCH.md`](../_ARCH.md)，由 `runner.py` 实现。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出定时备份入口 `sync_tick`、`record_manual_success`、状态存取与告警组件名；运行器与存储适配从各自模块导入 | ✅ |
| `runner.py` | 核心 | 一次备份与远程恢复：捕获快照 → 上传（指数退避重试）→ 轮转；远程恢复只合并。结果以 `RemoteBackupResult` / `RemoteRestoreResult` 返回（失败码 `snapshot` / `upload` / `internal`，已有一次在运行时为 `busy`）；远程文件名的唯一写法与轮转规则 | ✅ |
| `storage/` | 子包 | 存储适配：`RemoteBackupStrategy` 契约与 WebDAV / S3 两种实现，见 [`storage/_ARCH.md`](storage/_ARCH.md) | ✅ |
| `schedule.py` | 核心 | 纯规则（时钟由调用方传入，无 I/O）：间隔钳制、是否到期、是否值得告警 | ✅ |
| `state.py` | 核心 | 上次结果的单文件 JSON 持久化（整体原子替换，读到异常内容回落默认）；`tag()` 取本实例标记 | ✅ |
| `job.py` | 核心 | 一个 tick 的编排：设置 → 策略（`strategy_from_config`）→ 一次备份 → 记录结果 → 连续失败告警；设置、时钟、记忆管理器、存储与告警全部由调用方传入，不依赖调度器即可测试 | ✅ |

## 依赖方向

`app/lifecycle/schedulers.py` 与 `app/api/memory/operations/backup_remote.py` → 本目录。包内单向：`job.py` → `runner.py`、`schedule.py`、`state.py`、`storage/`；`schedule.py` → `state.py`；`runner.py` → `storage/`（仅类型）与 `memory/backup/snapshot.py`；`state.py` 与 `storage/` 不依赖包内其他模块。对外依赖 `instance_archive/{models,auto_backup/store}`、`services/event/app_event_bus`。本目录不依赖 API 层与 lifecycle：一次备份不知道自己被谁调度。
