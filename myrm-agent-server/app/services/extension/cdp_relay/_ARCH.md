# cdp_relay/ — Extension CDP loopback relay

## 职责

将 MV3 扩展的 `chrome.debugger` 流量转为 Playwright `connect_over_cdp` 可用的 loopback DevTools endpoint。

| 文件 | 职责 |
|------|------|
| `protocol.py` | Relay 常量与命令类型（attach / detach / cdp / createTab / closeTab） |
| `models.py` | 中继内部记录：CDP 客户端、已附加标签页、扩展身份；`CdpRequest`（一次客户端请求，自带 JSON-RPC 应答） |
| `extension_link.py` | 到扩展的命令通道：命令序号与超时、按序号匹配扩展回复/错误、浏览器身份（桥的最底层） |
| `targets.py` | 标签页镜像与会话：附加/释放/关闭、`Target.attachedToTarget` / `detachedFromTarget` 通告、CDP 事件分发；目标 id 只认扩展返回的真实 id（桥的中间层） |
| `contexts.py` | 虚拟浏览器上下文：`Target.createBrowserContext` 的归属分组——同一上下文里 Agent 打开的标签页随 dispose 或所属连接断开一并关闭；与用户浏览器共享 cookie 与存储，不是隔离 profile |
| `browser_methods.py` | Browser.* / Target.* 浏览器级方法的分派表（方法名 → 处理函数，含 `createTarget` / `closeTarget` / 虚拟上下文）；未支持的方法如实返回 `-32601` |
| `bridge.py` | 桥的顶层 `ExtensionCdpRelayBridge`：CDP 客户端帧解析、会话级请求转发、`probe_automation_ready()` |
| `server.py` | 127.0.0.1 HTTP `/json/*`（带与不带尾斜杠）+ `/cdp` WebSocket；仅放行本机自动化客户端：Host 必须是回环，带 `Origin` 的请求（网页发起）一律 403 |
| `manager.py` | 单例生命周期，绑定 ExtensionBridgeService WS；`relay_cdp_ready` 带短 TTL 探针缓存 |

桥由下而上单向继承：`ExtensionLink` → `TargetRegistry` → `ContextRegistry` → `BrowserMethods` → `ExtensionCdpRelayBridge`；每层只依赖下层，状态由各层自己的 `__init__` 持有。

## 健康 SSOT

`relay_cdp_ready` = loopback endpoint 已启动 **且** `Browser.getVersion` CDP 往返成功（非仅 transport 绑定）。

## 边界

- 仅 server 层；harness 通过 ExtensionBridge Protocol 调用，不 import 本包。
- 域名授权在 MV3 扩展边缘执行（createTab、navigate_url、Page.navigate）；`closeTab` 只作用于扩展登记的 Agent 标签页（其余回报 `closed:false`，relay 照样 detach 并遗忘）；server relay 信任扩展 gate。
