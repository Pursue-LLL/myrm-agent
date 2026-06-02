# companion 模块架构


---

## 架构概述

Companion（宠物伙伴）API 模块。提供 Observer 反应生成和进化状态查询两个端点，为前端 Companion 系统提供后端支撑。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 模块入口 | 空 | ❌ |
| `router.py` | ✅ 核心 | Companion API 端点定义（Observer 反应 + 进化状态） | ✅ |

---

## API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| `POST` | `/companion/react` | 生成宠物对最新助手消息的反应（Observer） |
| `GET` | `/companion/evolution-status` | 查询用户活跃度指标和进化资格 |

---

## 依赖关系

### 内部依赖
- `app.api.dependencies` (POS: 全局依赖注入)
- `app.core.channel_bridge.config_loader` (POS: 用户模型配置加载)
- `app.database.connection::get_db` (POS: 数据库会话工厂)
- `app.database.models::Chat, Message` (POS: 数据库 ORM 模型)

### 外部依赖
- `litellm`：LLM 调用（Observer 反应生成）
- `fastapi`：路由和依赖注入
- `pydantic`：请求/响应模型验证
- `sqlalchemy`：数据库查询（进化指标统计）
