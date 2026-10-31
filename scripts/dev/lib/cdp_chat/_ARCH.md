# cdp_chat 模块架构

WebUI chat 自动化：transport / bootstrap / input / submit / turn / support 拆分。

| 文件 | 职责 |
|------|------|
| `transport.py` | CDP/MCP transport 抽象 |
| `bootstrap.py` | 页面/chat 引导 |
| `input.py` / `submit.py` / `turn.py` | 输入与回合观测 |
| `support.py` | E2E API URL、Goal SSE、provider ready |
| `ui.py` | 稳定导出层 |
| `send_turn_contract.py` / `resume_turn_contract.py` | 回合契约 SSOT（含 `format_api_poll`：页面消息轮询的 404 / 失败 / 最慢耗时进发送日志；`format_turn_trace`：本次发送收到的 SSE 事件与时间、发送 promise 的结束方式进发送日志与失败摘要；`format_store_timeline`：本次发送期间页面消息列表的变化（聊天 id、用户/助手消息数、loading；丢失用户消息或换聊天时带写入者的调用栈）进同样两处） |
| `resume.py` | ResumeTurnContract STREAM_CONVERGE 执行器 |
| `live_turn_wait.py` | LIVE turn wait SSOT（parallel mux steer-first recovery） |
| `mcp_ui.py` | Chat UI session（Chrome DevTools MCP mux owner model） |

根级 `cdp_chat_*.py` 不存在；canonical 实现在本目录，调用方经 `from cdp_chat.* import ...` 导入。
