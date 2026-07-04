# services/wiki 模块架构


## 架构概述

Wiki 知识库服务层。提供记忆到 Wiki 的转换等业务逻辑。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 | — |
| `memory_to_wiki.py` | 核心 | 记忆转 Wiki 页面服务（单租户沙箱, 依赖环境变量） | ✅ 完整 |
| `obsidian_adapter.py` | 适配器 | Obsidian Vault 导入预处理：YAML Frontmatter 解析、`![[img]]` 嵌入图片迁移、`.canvas` JSON 文本提取、内容清洗后写入 wiki raw 目录 | ✅ 完整 |
