# core/types 模块架构


---

## 架构概述

业务层类型定义。提供跨模块共享的业务类型和文件引用类型。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `business.py` | ✅ 核心 | 业务层通用类型定义：ModelConfig、MCPServerConfig（含 mTLS 字段；结果缓存为 `cache_ttl_seconds` + `cacheable_tools` 显式 opt-in，空/0 关闭；`auth_provider`、`oversized_result_handler`、`elicitation_handler` 由业务层运行时注入，不进 JSON schema，请求体里携带非空值一律 422）等 |
