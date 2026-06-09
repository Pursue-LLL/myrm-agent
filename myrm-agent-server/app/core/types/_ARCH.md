# core/types 模块架构


---

## 架构概述

业务层类型定义。提供跨模块共享的业务类型和文件引用类型。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `business.py` | ✅ 核心 | 业务层通用类型定义：ModelConfig、MCPServerConfig（含 mTLS 字段）等 |
| `file_reference.py` | ✅ 辅助 | 文件引用类型定义 |
