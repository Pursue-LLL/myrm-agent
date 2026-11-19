# cdp_chat/support/chat 模块架构

不经浏览器、只走 REST 的聊天侧辅助：会话调用、落库消息证据、浏览器接管状态、agent-stream 回合与澄清回合。
证据一律取自落库消息，不取自提示词文本；`session.fetch_chat_messages` 是包内唯一读消息入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 标记 | 子包标记，只有一行说明、不重导出；包外一律经 `cdp_chat.support` 门面取名 | — |
| `session.py` | 基础 | 聊天会话的 REST 调用：创建、取消在途 agent 流、读消息、steer | ✅ |
| `evidence.py` | 核心 | 落库消息对一回合的证明：真实 file-write 工具调用及其空内容失败、最新助手消息里的 OK / DONE、用户消息数；`stored_reply_matches` 是各项「最新助手回复是否匹配」检查共用的判断，澄清回合的跳过完成检查也用它 | ✅ |
| `takeover.py` | 核心 | REST 侧的浏览器接管：mux 探针退化时的工具进度、待接管续跑用的 id、拒绝过期审批 | ✅ |
| `stream.py` | 核心 | 不经浏览器的 agent-stream 回合：对一次 POST 采集 SSE，直到截止、空闲或终止事件；及追问回合 | ✅ |
| `clarify.py` | 核心 | 澄清回合：发起到出卡、跳过未答卡，并据落库消息判断是否有待答卡、跳过是否抵达 agent | ✅ |

## 模块依赖

- `session` ← `evidence` · `takeover` · `clarify`
- `stream` · `evidence` ← `clarify`
- 包内上游：`support.api_client`（全部）· `support.timeouts`（`session` · `stream`）
- 包外：`cdp_chat.clarify_skip`（`clarify`；纯函数判据）
