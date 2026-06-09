# skills/store 模块架构


---

## 架构概述

Skill 商店模块。管理 Skill 的 CRUD、用户配置、读取和安全清洗。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `service.py` | ✅ 核心 | Skill 商店服务（CRUD、搜索、安装） |
| `reader.py` | ✅ 核心 | Skill 读取器（解析 Skill 包内容） |
| `user_config.py` | ✅ 辅助 | 用户 Skill 配置（个人偏好、启用/禁用） |
| `sanitizer.py` | ✅ 辅助 | Skill 清洗器（代码安全过滤） |
