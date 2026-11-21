# turn_lease/

## 架构概述

服务端自己启动的回合（目标续跑、审批超时后的自动恢复、重启后重放被打断的回合、后台任务完成后的唤醒回合）没有 HTTP 请求，停止信号只能经「会话占用 + `CancellationRegistry` 令牌」到达。本包把聊天回合的这套原语收成一个租约，让四处自启入口用同一份实现，且回合以任何方式结束都归还。改写聊天历史的操作（回退）不是回合，没有可停止的东西，只需要占住会话：它用同一份占用实现里不带令牌的 `hold_chat`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 门面 | 对外入口 `server_turn_lease`、`hold_chat` | ✅ |
| `lease.py` | ✅ 核心 | `server_turn_lease(session_id, turn_id)`：`gateway.reserve_session` + 注册 `CancellationToken(request_id=turn_id)`；退出时注销令牌、回合被取消则结束该会话的后台任务（与聊天「停止」一致）、仅在流未接管时归还自己的预留（按 `turn_id` 校验，不会释放期间抢到会话的消息回合的预留）。`hold_chat(chat_id)`：只 `gateway.reserve_session`，没有消息 id、不注册令牌，所以聊天「停止」得到「没有活动的智能体」（404）、紧急停止无物可取消、不会去结束该聊天的后台任务；预留在第一个挂起点之前取得；退出时仅在流未接管时归还；会话被占用抛 `AgentBusyError`、应用排空抛 `AgentDrainingError`，被拒时不动对方的预留 | ✅ |

## 边界

- `server_turn_lease` 只给服务端自启的回合用；聊天回合（`stream_session/`）与请求绑定的入口（OpenAI 兼容、语音）有各自的 HTTP 生命周期，不经此处。`hold_chat` 只给改写聊天历史的操作用（回退），它不是回合，不要拿它起回合。
- 调用点由 `tests/services/agent/turn_lease/test_server_started_turns_guard.py` 钉死：新增 `ai_agent_service_stream(` 调用必须在白名单里登记，自启回合必须走租约；唤醒回合不经 `ai_agent_service_stream`，其发起处只能是 `adaptive_wakeup/wake_turn_scheduler.py`，且必须在租约下；只有本包与聊天回合自己可以占会话、注册取消令牌，业务层占会话（回退）一律经 `hold_chat`。

## 依赖

- `app/services/agent/gateway.py`（会话预留 / 排空）
- harness `utils/runtime/cancellation`（`CancellationRegistry` / `CancellationToken`）、`api.hooks.get_background_registry`
