# UI Interaction Service Architecture (`_ARCH.md`)

## 1. 模块定位与职责 (Item 28 · P0)
本服务位于 `app/services/ui_interaction/`，作为 Server 业务层的反向交互协调中枢，协同底层 Harness 框架的 `ExtensionUIContext` 与前端/外部客户端进行双向交互握手：
- **挂起状态管理**：按 `chat_id` 维护正在等待用户响应的 `UIRequest` 队列；
- **反向握手分发**：当用户在 WebUI、Desktop 或渠道客户端提交响应时，通过 `resolve_response` 唤醒挂起的协程。

## 2. 核心文件
| 文件 | 职责与能力 | 核心契约 |
| :--- | :--- | :--- |
| `ui_request_manager.py` | 维护会话维度的请求状态机与上下文映射 | 线程安全，强类型，零 `Any` |
| `__init__.py` | 服务公共门面导出 | 导出 `UIRequestManager` 与 `get_ui_request_manager()` |

## 3. 设计红线
1. 单文件行数受控在 `< 300 行`；
2. 严格零 `Any` 类型注解；
3. 纯单机场景，内存状态机生命周期与 chat session 绑定。
