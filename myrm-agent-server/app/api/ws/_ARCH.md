# api/ws/

## 架构概述

WebSocket 连接两端的控制器：连接恢复（带抖动指数退避的状态机）与心跳探测（自适应间隔、死线截断）。两个控制器都是不依赖网络库的纯 Python 类，发送 Ping、关闭 socket 这类动作由调用方注入。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出连接恢复与心跳探测两组控制器及其配置 / 统计类型 | ✅ |
| `connection_controller.py` | 未接入 | `ConnectionController` 连接状态机（connected / connecting / disconnected）与 `JitteredBackoffScheduler`：0.5s、1s、2s、4s、8s、10s 六档上限，实际延迟取上限的 50%–100% 随机抖动，超过最高档后耗尽并返回 0；网络离线挂起重试，上线重置退避序号，「立即重连」以 0.5s 防抖打断当前等待 | ✅ |
| `heartbeat.py` | 未接入 | `AdaptiveHeartbeatController`：每个周期先检查上一轮 Pong 是否超时，超时或 Ping 发送失败即经注入的 `socket_closer` 关闭连接；默认活跃间隔 2s、空闲间隔 15s、Pong 死线 2s，间隔随调用方标记的工作负载状态切换；提供启动 / 停止后台轮询协程 | ✅ |

## 边界

- 控制器只做判断与计时：`ping_sender`、`socket_closer` 与状态订阅回调都由调用方注入，本包不持有 socket。
- 「是否有进行中的工作」由调用方通过 `mark_workload_state` 告知，心跳控制器不自行推断。
- 「未接入」：`app/` 内没有本包以外的导入，只有下面的测试引用；前端有同名的 TypeScript 版本（`myrm-agent-frontend/src/lib/connection/connection-controller.ts`、`jitter-backoff.ts`），同样没有产品入口可达的导入（`bun run verify:orphans` 列出）。

## 测试

- `tests/unit/core/ws/test_adaptive_heartbeat_and_recovery.py` — 心跳健康周期、Pong 死线超时关闭 socket、按工作负载切换间隔；退避档位与上限、抖动夹取、耗尽后停止重试；连接控制器的离线 / 上线转移、立即重连防抖、状态订阅通知
