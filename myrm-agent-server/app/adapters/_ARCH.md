# app/adapters 模块架构


---

## 架构概述

Framework Protocol 实现层（Business Layer 的 harness 适配器）。

本模块提供对 `myrm-agent-harness` 框架 Protocol 的具体实现，使用 Server 层的技术栈（SQLAlchemy、SQLite 等）。

---

## 设计原则

### 1. Protocol-Driven 设计

**框架层（harness）负责**：
- 定义 Protocol 接口（如 `SkillBackendProtocol`, `StorageProtocol`）
- 提供默认实现（如 `InMemoryStorage`）
- 核心业务逻辑（如 Skill Optimization 引擎）

**业务层（server/adapters）负责**：
- 实现框架 Protocol（使用业务技术栈）
- 适配数据存储（SQLite、S3 等）
- 与业务系统集成

### 2. 与 repositories/ 的区别

| 概念 | 职责 | 示例 |
|------|------|------|
| **adapters/** | 实现框架 Protocol | `SQLAlchemyStorage` 实现 `StorageProtocol` |
| **repositories/** | 业务特定的数据访问 | `ChatHistoryRepository` 管理聊天记录 |

**关键区别**：
- `adapters/`: 无需理解业务逻辑，只需实现框架接口
- `repositories/`: 包含业务规则、查询优化、事务管理等

---

## 当前模块清单

### skill_optimization/

**职责**：实现 PyPI `myrm_agent_harness.agent.skills.optimization` 的 Storage Protocol

**框架 Protocol**：
```python
# myrm_agent_harness.agent.skills.optimization.protocols
class SkillQualityDataSource(Protocol):
    async def get_quality_history(...) -> list[dict]: ...
    async def save_quality_score(...) -> None: ...
```

**Server 实现**：
```python
# server/app/adapters/skill_optimization/sqlalchemy_storage.py
class SQLAlchemyStorage(SkillOptimizationStorage):
    """SQLAlchemy implementation of SkillOptimizationStorage Protocol
    
    支持两种session管理模式：
    - 固定session（API请求级，FastAPI依赖注入）
    - session_factory（scheduler等长生命周期组件）
    """
    def __init__(self, session=None, session_factory=None): ...
```

**包含的 Repository**：
- `OptimizationRepository`: 优化记录 CRUD
- `ABTestRepository`: A/B 测试数据
- `QualityRepository`: 质量评分历史
- `SnapshotRepository`: Skill版本快照 CRUD（支持版本回滚和对比）
- `BatchTaskRepository`: 批量任务管理
- `AuditLogRepository`: 审计日志

**ORM 模型**（`app/database/models/skill_optimization/`）：
- `SkillVersionModel`: Skill版本表（复合主键 skill_id + version）
- `BatchSnapshot`: 批量优化前技能快照（支持 cancel/rollback）

---

## 与 harness 的关系

### 依赖方向（正向，符合架构原则）

```
┌─────────────────────────────────────┐
│ myrm_agent_harness.agent.skills.optimization │ ← 框架层（Protocol 定义）
│ - protocols.py (StorageProtocol)    │
│ - in_memory_storage.py (默认实现)    │
└─────────────────────────────────────┘
            ↑ 依赖（实现接口）
┌─────────────────────────────────────┐
│ server/app/adapters/                │ ← 业务层（Protocol 实现）
│ - skill_optimization/               │
│   - sqlalchemy_storage.py           │
└─────────────────────────────────────┘
```

**关键点**：
- ✅ Server 依赖 harness（正向依赖）
- ✅ harness 不知道 server 的存在（零反向依赖）
- ✅ 符合依赖倒置原则（DIP）

---

## 未来扩展指南

### 添加新的 Protocol 实现

当 harness 定义新的 Protocol 时，在 `app/adapters/` 下创建新的实现：

**示例：Memory System Adapter（未来扩展）**

```python
# PyPI myrm-agent-harness 公开的 Protocol 定义
class MemoryBackendProtocol(Protocol):
    async def store_memory(...) -> None: ...
    async def retrieve_memory(...) -> list[Memory]: ...

# app/adapters/memory/
├── __init__.py
└── sqlite_backend.py  # Server 侧实现（SQLite on persistent volume）
```

### 与 repositories/ 的协作

如果 Protocol 实现需要复杂的数据访问逻辑，可以创建对应的 Repository：

```python
# app/adapters/memory/sqlite_backend.py
from app.repositories.memory import MemoryRepository  # 如果需要

class SQLiteMemoryBackend:
    def __init__(self, session: AsyncSession):
        self.repo = MemoryRepository(session)

    async def store_memory(self, ...):
        return await self.repo.create_with_embedding(...)
```

---

## 最佳实践

### 1. 保持适配器简单

❌ **错误示例**（包含业务逻辑）：
```python
class SQLAlchemyStorage:
    async def save_quality_score(self, score):
        # ❌ 不应该在 adapter 里做业务判断
        if score < 0.5:
            await self.send_alert()  # 业务逻辑
        await self.repo.save(score)
```

✅ **正确示例**（纯粹的数据适配）：
```python
class SQLAlchemyStorage:
    async def save_quality_score(self, score):
        # ✅ 只负责数据存储，不包含业务逻辑
        await self.repo.save(score)
```

### 2. 遵循 Protocol 契约

```python
# 框架定义的 Protocol
class StorageProtocol(Protocol):
    async def save(self, data: dict) -> str:
        """Returns: record_id"""
        ...

# ✅ 正确：完全遵循契约
class SQLAlchemyStorage:
    async def save(self, data: dict) -> str:
        record = await self.repo.create(data)
        return record.id  # 返回 str

# ❌ 错误：返回类型不匹配
class SQLAlchemyStorage:
    async def save(self, data: dict) -> dict:  # 应该返回 str
        return await self.repo.create(data)
```

### 3. 错误处理

```python
# ✅ 将底层异常转换为框架异常
from myrm_agent_harness.agent.skills.optimization.exceptions import StorageError

class SQLAlchemyStorage:
    async def save(self, data: dict) -> str:
        try:
            return await self.repo.create(data)
        except SQLAlchemyError as e:
            # 转换为框架异常
            raise StorageError(f"Failed to save: {e}") from e
```

---

## 参考架构

### langchain 的设计

```python
# langchain/storage/_base.py
class BaseStore(ABC):
    """Abstract base class for storage"""
    @abstractmethod
    def mset(self, key_value_pairs): ...

# langchain/storage/redis.py
class RedisStore(BaseStore):
    """Redis implementation"""
    def mset(self, key_value_pairs):
        # Redis-specific implementation
```

### 我们的对标

```python
# myrm_agent_harness.agent.skills.optimization.protocols
class StorageProtocol(Protocol):
    """Abstract storage interface"""
    async def save(self, data): ...

# server/app/adapters/skill_optimization/sqlalchemy_storage.py
class SQLAlchemyStorage:
    """SQLite implementation via SQLAlchemy"""
    async def save(self, data):
        # SQLite-specific implementation
```

---

## 文档导航

- 框架层技能后端：`myrm_agent_harness.backends.skills`（PyPI `myrm-agent-harness`）
- 框架层技能优化：`myrm_agent_harness.agent.skills.optimization`（PyPI `myrm-agent-harness`）
- [server/ARCHITECTURE.md](../../ARCHITECTURE.md) — Server 总体架构
