# cdp_relay/ — Extension CDP loopback relay

## 职责

将 MV3 扩展的 `chrome.debugger` 流量转为 Playwright `connect_over_cdp` 可用的 loopback DevTools endpoint。

| 文件 | 职责 |
|------|------|
| `protocol.py` | Relay 常量与命令类型（attach / detach / cdp / createTab） |
| `bridge.py` | Target.* 合成 + CDP 客户端处理 + `probe_automation_ready()` |
| `server.py` | 127.0.0.1 HTTP `/json/*` + `/cdp` WebSocket |
| `manager.py` | 单例生命周期，绑定 ExtensionBridgeService WS；`relay_cdp_ready` 带短 TTL 探针缓存 |

## 健康 SSOT

`relay_cdp_ready` = loopback endpoint 已启动 **且** `Browser.getVersion` CDP 往返成功（非仅 transport 绑定）。

## 边界

- 仅 server 层；harness 通过 ExtensionBridge Protocol 调用，不 import 本包。
- 域名授权在 MV3 扩展边缘执行（createTab、navigate_url、Page.navigate）；server relay 信任扩展 gate。
