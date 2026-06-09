# core/storage 模块架构


---

## 架构概述

文件存储服务。提供文件的增删改查功能和智能缓存存储（Smart Cached Storage），支持生命周期管理。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `service.py` | ✅ 核心 | 文件服务，提供文件 CRUD 功能 |
| `smart_cache.py` | ✅ 辅助 | 薄包装层，re-export 框架 `CachedStorageProvider` as `SmartCachedStorage` |
| `models.py` | ✅ 辅助 | 存储相关数据模型定义 |
| `lifecycle.py` | ✅ 辅助 | 文件生命周期管理（过期清理等） |

---

## 依赖关系

- `app/database/`：文件元数据持久化
- `app/config/`：存储配置
