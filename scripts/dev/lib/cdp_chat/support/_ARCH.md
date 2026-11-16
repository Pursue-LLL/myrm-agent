# cdp_chat/support 模块架构

E2E 聊天自动化的底层辅助包：被测栈的 API/UI 地址与仅回环 HTTP、聊天页绑定、就绪等待、并行负载下的等待预算、后端日志、Goal 状态，另有按主题分组的子包 `chat/` 与 `config/`。
`__init__.py` 是包外唯一入口（`from cdp_chat.support import ...`），只重导出、不定义任何东西；包内模块互相引用定义处模块，依赖无环。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 门面 | 包外代码用到的名字的稳定导入面（`__all__`），每个名字取自定义它的模块 | ✅ |
| `paths.py` | 基础 | `MONOREPO_ROOT`：检出根的唯一来源，由本文件位置推出，其余模块只读它 | ✅ |
| `timeouts.py` | 核心 | 并行运行下各类等待的墙钟预算：按活跃 wave 租约、并行用例数与 mux 对端数缩放基础超时 | ✅ |
| `api_client.py` | 核心 | E2E API/UI 来源解析与仅回环 HTTP：并行负载下重试，共享 dev 后端拒连时先做一次崩溃自愈 | ✅ |
| `binding.py` | 核心 | 把聊天页绑定到被测后端：向页面写入运行时身份与 API base 的脚本，及读回校验（不一致即 fail-closed） | ✅ |
| `readiness.py` | 核心 | 轮询被测各部分可接活：provider、后端健康、Chrome CDP、前端 dev server 首次编译 | ✅ |
| `goal.py` | 核心 | 聊天的 Goal 状态（goal Chrome E2E 断言的证据）：持久化判据、读取与轮询、推动状态 | ✅ |
| `page_js.py` | 辅助 | 在聊天页里 evaluate 的纯字符串脚本：页面与 bridge 探针、模型选择、关弹窗、重置聊天、E2E bridge 安装器、流 API 绑定 | ✅ |
| `backend_log.py` | 辅助 | 定位被测栈的 `backend.log`，按偏移读取一次运行期间记录的内容，失败时转储 | ✅ |
| `chat/` | 子包 | 聊天会话、落库消息证据、浏览器接管、agent-stream、澄清，见 [chat/_ARCH.md](chat/_ARCH.md) | — |
| `config/` | 子包 | 全局配置记录读写与 E2E 固定配置，见 [config/_ARCH.md](config/_ARCH.md) | — |

## 模块依赖

包内（`A ← B` 表示 B 依赖 A）：

- `paths` ← `timeouts` · `api_client` · `backend_log`
- `api_client` ← `binding` · `readiness` · `goal` · `backend_log` · `chat/*` · `config/*`
- `timeouts` ← `binding` · `readiness` · `chat/session` · `chat/stream` · `config/store`
- `binding` ← `backend_log`

包外：`e2e_core`（`dev_ports`、`real_user_home`、`stack_mutation_policy`、`epoch_delivery_plane`）· `dev_gate.contract` · `mux.transport_supervisor` · `cdp_chat.clarify_skip`（仅 `chat/clarify`）。

## 补丁作用域

补丁只影响读取该名字的模块。包外代码在调用时经门面按名字读取，打在门面上的补丁对它们有效；包内模块持有的是定义处模块里的名字，测试要给读者所在的模块打补丁（例如 `cdp_chat.support.chat.evidence.fetch_chat_messages`），打在门面上到不了包内读者。
