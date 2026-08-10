# background_job/

## 架构概述

后台 bash 任务业务域：启动期 Store 配置与 orphan reconcile、任务 finish 的 WebUI 闭环通知。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `background_job_startup.py` | ✅ 核心 | 启动 configure `BackgroundJobStore`（harness_dir/.myrm/background_jobs.db）并 reconcile orphaned running 行 | ✅ |
| `background_job_finish_handler.py` | ✅ 核心 | Harness 后台 bash 自然退出时的 WebUI 闭环：Store finish 幂等 → locale 双语完成消息 → `append_message` → `goal_wait_background_resume` → `SYSTEM_NOTIFICATION` SSE | ✅ |

## 依赖

- 父模块 [`agent/_ARCH.md`](../_ARCH.md)
- `goals/goal_wait_background_resume`（WAIT 恢复）
- harness `api.hooks::BackgroundJobFinishResult`
