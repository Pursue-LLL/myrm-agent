# app/services/extension/bridge 子包架构

浏览器扩展桥。`ExtensionBridgeService` 的行为按关注点拆成六个 mixin，状态集中在 `__init__`；`app.services.extension.bridge` 导入路径不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 `ExtensionBridgeService`、`get_extension_bridge`、`DomainPolicyWarning` 与 harness 契约类型（`ExtensionTab` / `ExtensionStatus` / `ExtensionBridgeNotAvailable`） | — |
| `common.py` | 辅助 | logger、心跳常量、能力映射、`DomainPolicyWarning`、`_broadcast_extension_status`、`get_cdp_relay_manager`（**测试唯一打桩点**）、harness 契约类型 `ExtensionTab` / `ExtensionStatus` / `ExtensionBridgeNotAvailable` 的统一出口 | ✅ |
| `service.py` | 核心 | `ExtensionBridgeService`：`__init__` 中全部会话状态（ws、capabilities、tabs、pending futures、心跳/接收任务、锁、playwright） | ✅ |
| `connection.py` | 核心 | connect / connect_to_domain（返回 harness 的 `ExtensionBrowserInstance`：用户自己的浏览器，池不为其上下文加覆盖、不让页面空闲留存）/ navigate / get_status / disconnect、CDP endpoint 解析（含 Playwright 与 direct 两种来源）、relay_cdp_ready、Playwright driver 缓存（`_ensure_playwright` / `_discard_playwright`；连接因 driver 进程已退出而失败时 `_attach_once` 丢弃缓存，`_connect_over_cdp` 在同一次调用里换新 driver 再连一次）；对宿主与兄弟 mixin 的依赖以类级注解和仅供类型检查的 `TYPE_CHECKING` 桩声明（运行时不存在，不遮蔽兄弟的真实方法） | ✅ |
| `access.py` | 核心 | 域名策略匹配与校验、授权域名读写、策略归属（用户设过策略才在握手时推送；扩展握手后的首份回报只在用户没设过时采用）、策略 payload 应用与变更通知、domain policy 警告 | ✅ |
| `relay.py` | 核心 | WebSocket 握手/读循环/心跳循环、请求-响应 future、tab 同步（新页面有了文档才把 opener 交给 relay）与焦点、debugger attach、tab 刷新 | ✅ |
| `tabs.py` | 核心 | 扩展标签页列表的镜像（含哪些是 Agent 的、各由哪个 Agent 标签页开出）、`list_tabs` 与 tab 移动请求 | ✅ |
| `capability.py` | 核心 | capability 规范化与 `_require_capability` / `_require_action_capability` 守卫 | ✅ |
| `clip_config.py` | 核心 | 向扩展推送 clip-agent 配置 | ✅ |
| `factory.py` | 核心 | 进程级单例 `_bridge_instance` / `get_extension_bridge` | ✅ |

## 依赖关系

- 上游：`app.services.extension.access_policy`、`cdp_relay.manager` / `cdp_relay.protocol`、`app.services.event`、harness 扩展桥类型（可选）
- 下游：`app/api/extension/*`、`app/lifecycle/browser.py`、`tool_setup/browser.py`（浏览器工具按需取 bridge）
