# core/channel_bridge/providers 模块架构


---

## 架构概述

业务层 channel providers。所有通用 IM 通道实现已内置到框架层
（`app.channels.providers`），此目录仅保留：
- **ChatChannel**：应用内消息推送（ORM 写入，纯业务逻辑）
- **API 客户端辅助**：连接测试端点使用的 DingTalkClient 等

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 入口 | 模块声明 | ❌ |
| `chat.py` | ✅ 核心 | ChatChannel：应用内消息推送，将 OutboundMessage 写入 Chat + Message 表 | ✅ |
| `dingtalk_api.py` | ✅ 辅助 | DingTalkClient：钉钉 OpenAPI 客户端，供 router.py 连接测试使用 | ✅ |
| `http_timeout.py` | ✅ 辅助 | 共享 HTTP 超时解析（env 覆盖 + 安全 clamp） | ✅ |

---

## 依赖关系

### 内部依赖
- `app.channels`：BaseChannel 抽象基类
- `../../database/`：Chat, Message ORM（仅 ChatChannel 使用）

### 外部依赖
- `httpx`：DingTalkClient HTTP 请求
