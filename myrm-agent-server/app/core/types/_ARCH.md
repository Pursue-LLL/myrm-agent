# core/types 模块架构


---

## 架构概述

业务层类型定义。提供跨模块共享的业务类型和文件引用类型。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `business.py` | ✅ 核心 | 业务层通用类型定义：ModelConfig、MCPServerConfig（含 mTLS 字段；结果缓存为 `cache_ttl_seconds` + `cacheable_tools` 显式 opt-in，空/0 关闭）等 |
