# core/storage 模块架构


---

## 架构概述

文件存储服务。提供文件的增删改查功能。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `service.py` | ✅ 核心 | 文件服务，提供文件 CRUD 功能 |
| `models.py` | ✅ 辅助 | 存储相关数据模型定义 |

---

## 依赖关系

- `app/platform_utils/`：`get_storage_provider()` 延迟获取框架存储单例
- `myrm_agent_harness.toolkits.storage`：`StorageProvider` 抽象、路径约定与 `FilePurpose`；文件内容与元数据均经它读写
