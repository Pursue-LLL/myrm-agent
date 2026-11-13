# cdp_relay/ — Extension CDP loopback relay

## 职责

将 MV3 扩展的 `chrome.debugger` 流量转为 Playwright `connect_over_cdp` 可用的 loopback DevTools endpoint。

| 文件 | 职责 |
|------|------|
| `protocol.py` | Relay 常量与命令类型（attach / detach / cdp / createTab / closeTab） |
| `models.py` | 中继内部记录：CDP 客户端、已附加标签页、扩展身份；`CdpRequest`（一次客户端请求，自带 JSON-RPC 应答） |
| `extension_link.py` | 到扩展的命令通道：命令序号与超时、按序号匹配扩展回复/错误、浏览器身份（桥的最底层）；交出一条回复后让等待它的调用方先把它转给 CDP 客户端，再处理扩展的下一条消息，保证回复不被它之后的事件抢先（见下「保序」）；扩展带 `code: tab_not_authorized` 的错误回报成 `TabNotAuthorized` |
| `targets.py` | 标签页镜像与会话：附加/释放/关闭、`Target.attachedToTarget` / `detachedFromTarget` 通告、CDP 事件分发；目标 id 只认扩展返回的真实 id；Agent 页面开出的新标签页（`RelayTabInfo.opener_tab_id` 指向已附加的页面）自动附加，并向拿到来源页面的客户端通告（带 `openerId`、沿用来源的虚拟上下文）；扩展拒绝一个标签页时整页放手（`_let_go_of_refused_tab`，见下「放手」）（桥的中间层） |
| `contexts.py` | 虚拟浏览器上下文：`Target.createBrowserContext` 的归属分组——同一上下文里 Agent 打开的标签页随 dispose 或所属连接断开一并关闭；与用户浏览器共享 cookie 与存储，不是隔离 profile |
| `browser_methods.py` | Browser.* / Target.* 浏览器级方法的分派表（方法名 → 处理函数，含 `createTarget` / `closeTarget` / 虚拟上下文）；未支持的方法如实返回 `-32601` |
| `bridge.py` | 桥的顶层 `ExtensionCdpRelayBridge`：CDP 客户端帧解析、会话级请求转发（唯一例外：`Page.bringToFront` 只应答不转发，不让自动化把用户的窗口拉到最前；被扩展以 `TabNotAuthorized` 拒绝的请求不应答，整页放手）、`probe_automation_ready()` |
| `server.py` | 127.0.0.1 HTTP `/json/*`（带与不带尾斜杠）+ `/cdp` WebSocket；仅放行本机自动化客户端：Host 必须是回环，带 `Origin` 的请求（网页发起）一律 403 |
| `manager.py` | 单例生命周期，绑定 ExtensionBridgeService WS；`relay_cdp_ready` 带短 TTL 探针缓存 |

桥由下而上单向继承：`ExtensionLink` → `TargetRegistry` → `ContextRegistry` → `BrowserMethods` → `ExtensionCdpRelayBridge`；每层只依赖下层，状态由各层自己的 `__init__` 持有。

## 保序

扩展经同一条 WebSocket 按 Chrome 的产出顺序送来回复与事件，且常成批到达。事件一到就转给 CDP 客户端，而回复要等调用方在下一个事件循环轮次恢复后才转出，不处理的话成批到达的事件会抢在它们之前的回复前面。Playwright 在 `Page.getFrameTree` 的回复里才登记生命周期监听，抢先到达的 `load` 等事件被丢弃：已加载完的新页面（Agent 点链接开出的标签页）的 `wait_for_load_state()` 就永远等不到。`ExtensionLink` 因此在交出每条回复或错误后让出一轮，让调用方先转发；`tests/services/extension/test_cdp_relay_ordering.py` 钉住这一次序。保证只覆盖调用方恢复后立刻作答的回复（会话级命令）；要经多次等待才作答的请求（如 `Target.createTarget`）不在其内。

## 放手

标签页不再在授权站点上时（点开的新标签页跳去别的站点最常见），扩展对发往它的每条 `cdp` 指令都以 `tab_not_authorized` 拒绝。逐条回错误会让 Playwright 的驱动进程崩溃：它用一批指令初始化新页面，只在稍后才 await 其中几条，先到的那个错误成了没人接的 rejection，Node 直接退出，Agent 的整条浏览器连接随之断掉。中继因此不回答被这样拒绝的指令，而是像 Chrome 关掉一个 target 那样放手整个页面：通告 `Target.detachedFromTarget`（Playwright 一次性让该页所有在途指令失败，这是它处理得了的），并让扩展释放调试器。其他任何失败仍照常逐条回错误。`tests/services/extension/test_cdp_relay_refusals.py` 钉住这一行为；扩展在 `agent_tabs.js` 认领新标签页时就不认领开往未授权站点的页面，桥（`bridge/relay.py::_sync_relay_tabs`）又只在新页面有了文档后才交给中继，重定向与空白页因此到不了客户端；放手只剩下「交出时仍在授权站点、随后很快离开」（页面加载后用脚本跳走、用户恰在此时撤销授权）。`test_popup_and_dialog_real_browser.py` 里用一组不同延迟的跳走页扫过这段初始化时间，指令被逐条回错误时会让驱动崩溃，所以它是这一行为的真实浏览器守卫（概率性触发，确定性的守卫是上面的单元测试）。

## 健康 SSOT

`relay_cdp_ready` = loopback endpoint 已启动 **且** `Browser.getVersion` CDP 往返成功（非仅 transport 绑定）。

## 边界

- 仅 server 层；harness 通过 ExtensionBridge Protocol 调用，不 import 本包。
- 域名授权在 MV3 扩展边缘执行（createTab、navigate_url、Page.navigate）；`closeTab` 只作用于扩展登记的 Agent 标签页（其余回报 `closed:false`，relay 照样 detach 并遗忘）；server relay 信任扩展 gate。
