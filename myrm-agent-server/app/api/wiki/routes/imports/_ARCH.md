# api/wiki/routes/imports/

## 架构概述

Wiki 批量导入：folder/zip 与 Obsidian 两条路径分开，`__init__.py` 按原顺序聚合为单一 router，保证 `/import/obsidian-zip` 仍先于通配路由匹配。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合两条导入路由，保持注册顺序 | ✅ |
| `folder_zip.py` | 路由 | `POST /import/folder` · `POST /import/zip`；文本经 harness `read_text_file` 解码（UTF-8、BOM、可识别的 GBK 等旧编码），编码无法可靠识别的文件跳过并记警告 | ✅ |
| `obsidian.py` | 路由 | `POST /import/obsidian` · `POST /import/obsidian-zip` 与 vault 遍历；响应的 `files_enqueued` 是实际入队的笔记数，`files_processed` 还含内容未变的笔记（重复导入同一 vault 时 `files_enqueued` 为 0） | ✅ |

## 依赖关系

- 各模块无横向依赖，全部通过 `__init__.py` 聚合。
