# cdp_chat/support/config 模块架构

全局配置记录的读写，以及一次 E2E 运行需要固定的配置：经 API 固定（`api_pins`），再经页面固定同样的值（`page_pins`），使页面的配置同步与后端一致。
全局 key 被所有并行 chrome_e2e 会话共享，写入走乐观锁加跨进程互斥。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 标记 | 子包标记，只有一行说明、不重导出；包外一律经 `cdp_chat.support` 门面取名 | — |
| `store.py` | 基础 | 配置记录读写：按 key 的跨进程 flock 互斥，带 `expectedVersion` 的乐观锁写入与有界重试 | ✅ |
| `api_pins.py` | 核心 | 经 API 固定一次 E2E 需要的后端配置：YOLO 与 HITL 模式、引导完成、记忆关闭、清空搜索服务；HITL 固定的重试策略与页面侧共用 | ✅ |
| `page_scripts.py` | 辅助 | 经页面自己的 API 层写固定配置、清空其离线队列的脚本字符串 | ✅ |
| `page_pins.py` | 核心 | 经页面固定同样的配置：PUT 走页面、先清离线队列，HITL 复位时重载 UI 后再固定一次 | ✅ |

## 模块依赖

- `store` ← `api_pins` ← `page_pins`；`page_scripts` ← `page_pins`
- 包内上游：`support.api_client`（`store` · `api_pins` · `page_pins`）· `support.timeouts`（`store`）
- 包外：`dev_gate.contract`（`page_pins` 取 `EvaluateIntent`，`api_pins` 取 HITL 固定的重试预算）· `e2e_core.dev_ports`（`page_scripts`）
