# toolkits/filesystem_suggest


## 架构概述

通用 **本地路径建议** 工具包（聊天 `@` 引用补全与 browse 搜索的后端原语）。只负责单机文件系统枚举、路径安全过滤和模糊排序；不包含 HTTP、chat_id、GUI 状态、多租户或业务存储语义。

`WorkspacePathIndexer` 是 workspace 文件列表的 **SSOT**（单一事实来源）：`GET /files/suggest`、`GET /files/browse/search` 与 server 的代码结构索引共用同一枚举器；前两者另共用 `rank_basename` 排序。

枚举有固定的文件数上限；列表达到上限时，目录里可能还有未列出的文件，调用方用 `WorkspacePathIndexer.is_truncated(files)` 判断，上限的取值与判定口径只在 `indexer.py` 内定义。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 path suggestion 公共 API | ✅ |
| `indexer.py` | 核心 | 有界文件枚举。优先 `git ls-files --cached --others --exclude-standard`（只列工作区子树，目录名按字面量 pathspec 处理，不读整个仓库），降级 `os.walk`，带短 TTL 缓存；`is_truncated` 告知列表是否触及枚举上限 | ✅ |
| `models.py` | 核心 | Workspace suggestion DTO 与选项模型 | ✅ |
| `suggest.py` | 核心 | GUI 友好的文件/目录建议排序；支持 basename 模糊匹配和 slash/path 目录模式 | ✅ |

## 消费方

| 层 | 位置 | 用途 |
|----|------|------|
| Server REST | `myrm-agent-server/app/api/files/suggest.py` | `GET /api/v1/files/suggest` — 聊天框 `@` 引用补全 |
| Server REST | `myrm-agent-server/app/api/files/browse.py` | `GET /api/v1/files/browse/search` — 文件浏览搜索 |
| Server 服务 | `myrm-agent-server/app/services/code_graph/service.py` | 代码结构索引的文件清单；用 `is_truncated` 把「清单被截断」写进索引统计 |
| Frontend | `services/chat.ts` | 调用上述 API |

**非 Agent 工具**：无 `*_agent_tools.py`，不进 tool registry，零 LLM token 占用。
