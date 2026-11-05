# app/services/agent/params/mention/references 子包架构

每类 `@` 引用一个处理器。处理器只负责"读这一种引用、产出一段 XML 片段、报告自己的字节数"；顺序与预算由 `../pipeline.py` 持有。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | `HANDLERS` 注册表：`ref.type` → async 处理器，顺序与调度链一致 | — |
| `git.py` | 核心 | `@staged` / `@diff`：读 git diff（`hardened_git_argv`），无改动时给明确占位 | ✅ |
| `folder.py` | 核心 | `@folder:`：工作区受限路径 + 200 条上限的目录树 | ✅ |
| `url.py` | 核心 | `@url:`：`FetchEngine` 抓取（SSRF 由引擎拦截），失败给错误片段 | ✅ |
| `workspace_file.py` | 核心 | `@file`：路径越界/敏感文件拒绝、行区间读取、Office 文档解析、内联预算 | ✅ |
| `stored_file.py` | 核心 | 上传/生成文件：从 `files_service` 读内容，PDF/Office 解析，二进制与超限降级 | ✅ |
| `codebase.py` | 核心 | `@codebase`：有上限的 `os.walk` 统计（无索引），引导 Agent 用 grep/glob 工具 | ✅ |
| `wiki.py` | 核心 | `@wiki:` 概念页与原始文件：经 `WikiStructure` 读取，缺失/超限给明确片段 | ✅ |
| `prior_chat.py` | 核心 | `@chat:`：召回索引的 summary + snippet；无痕网页会话拒绝、索引缺失时重建一次 | ✅ |
| `artifact_range.py` | 核心 | 产物选区：前端直传文本，仅做内联预算与空选区判定 | ✅ |

## 依赖关系

- 上游：`../context.py`（累加状态）、`../xml.py`（片段与预算）、`../documents.py`（文档解析）
- 下游：harness（path security / file parsers / web fetch / wiki / conversation search）、`app.core.storage`、`app.services.chat`
