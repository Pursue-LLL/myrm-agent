# turn_lease/

## 架构概述

服务端自己启动的回合（目标续跑、审批超时后的自动恢复、重启后重放被打断的回合、后台任务完成后的唤醒回合）没有 HTTP 请求，停止信号只能经「会话占用 + `CancellationRegistry` 令牌」到达。本包把聊天回合的这套原语收成一个租约，让四处自启入口用同一份实现，且回合以任何方式结束都归还。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 门面 | 对外入口 `server_turn_lease` | ✅ |
| `lease.py` | ✅ 核心 | `server_turn_lease(session_id, turn_id)`：`gateway.reserve_session` + 注册 `CancellationToken(request_id=turn_id)`；退出时注销令牌、回合被取消则结束该会话的后台任务（与聊天「停止」一致）、仅在流未接管时归还自己的预留（按 `turn_id` 校验，不会释放期间抢到会话的消息回合的预留） | ✅ |

## 边界

- 只给服务端自启的回合用；聊天回合（`stream_session/`）与请求绑定的入口（OpenAI 兼容、语音）有各自的 HTTP 生命周期，不经此处。
- 调用点由 `tests/services/agent/turn_lease/test_server_started_turns_guard.py` 钉死：新增 `ai_agent_service_stream(` 调用必须在白名单里登记，自启回合必须走租约；唤醒回合不经 `ai_agent_service_stream`，其发起处只能是 `adaptive_wakeup/wake_turn_scheduler.py`，且必须在租约下。

## 依赖

- `app/services/agent/gateway.py`（会话预留 / 排空）
- harness `utils/runtime/cancellation`（`CancellationRegistry` / `CancellationToken`）、`api.hooks.get_background_registry`
