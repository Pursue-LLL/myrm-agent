# cdp_chat 模块架构

WebUI chat 自动化：transport / bootstrap / input / submit / turn / support 拆分。

| 文件 | 职责 |
|------|------|
| `transport.py` | CDP/MCP transport 抽象 |
| `bootstrap/` | 页面/chat 引导，分层包：每层一个模块，后一层继承前一层，只调用本层和更早层的成员——`clock`（启动、会话、布局计时与停滞判定）· `binding`（API base 绑定、provider 与 React 水合等待、弹窗、mux 恢复、共享 UI 契约）· `shell_ready`（页面成为可用聊天壳的等待与自愈、新聊天复位）· `layout`（聊天首页水合与布局等待）· `surface`（`wait_shell_ready`、`navigate_to_chat`、`ensure_chat_surface`、`click_new_chat`）· `flow`（`CdpChatBootstrap`：deadline 切分、warm-shell 探测——热路径开关取自 `e2e_core/shared_ui_session/caps.py`、shell 与 bridge 两阶段）；`__init__.py` 导出 `CdpChatBootstrap`，测试按读取名字的子模块打补丁 |
| `input.py` / `submit.py` / `turn.py` | 输入与回合观测 |
| `support/` | E2E 聊天自动化的底层辅助包，分层包：`api_client`（API/UI 地址与仅回环 HTTP）· `binding`（聊天页绑定到被测后端）· `readiness`（provider、后端、CDP、前端就绪等待）· `timeouts`（并行负载下的等待预算）· `goal`（Goal 状态）· `page_js`（页内脚本）· `backend_log`（后端日志）· `paths`（检出根）；子包 `chat/`（会话、消息证据、浏览器接管、agent-stream、澄清）与 `config/`（配置记录读写、E2E 固定配置）；`__init__.py` 是包外唯一入口，只重导出、不定义；测试按读取名字的子模块打补丁，详见 [support/_ARCH.md](support/_ARCH.md) |
| `clarify_skip.py` | 澄清卡「跳过」的 API 判据（纯函数）：`skip_resume_value`（带卡片所属挂起的 id，键名与服务端 `INTERRUPT_ID_KEY` 一致）、`open_clarification` / `pending_clarification_interrupt_id`（从落库消息读最新未答卡与它的 id）、`continued_after_skip`（跳过之后出现文字、没有报错、没有再次出卡才算续跑；流只是结束不算证据，不寻址的跳过正是这样结束的）、`sse_message_text`；`support/chat/clarify.py` 的 `resume_clarify_skip_via_api` 与 `chat_has_pending_clarification` 经它判定 |
| `ui.py` | 稳定导出层 |
| `send_turn_contract.py` / `resume_turn_contract.py` | 回合契约 SSOT（含 `format_api_poll`：页面消息轮询的 404 / 失败 / 最慢耗时进发送日志；`format_turn_trace`：本次发送收到的 SSE 事件与时间、发送 promise 的结束方式进发送日志与失败摘要；`format_store_timeline`：本次发送期间页面消息列表的变化（聊天 id、用户/助手消息数、loading；丢失用户消息或换聊天时带写入者的调用栈）进同样两处） |
| `resume.py` | ResumeTurnContract STREAM_CONVERGE 执行器 |
| `live_turn_wait.py` | LIVE turn wait SSOT（parallel mux steer-first recovery） |
| `mcp_ui.py` | Chat UI session（Chrome DevTools MCP mux owner model） |

根级 `cdp_chat_*.py` 不存在；canonical 实现在本目录，调用方经 `from cdp_chat.* import ...` 导入。
