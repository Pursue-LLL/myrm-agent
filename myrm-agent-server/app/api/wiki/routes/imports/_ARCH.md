# api/wiki/routes/imports/

## 架构概述

Wiki 批量导入：folder/zip 与 Obsidian 两条路径分开，`__init__.py` 按原顺序聚合为单一 router，保证 `/import/obsidian-zip` 仍先于通配路由匹配。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合两条导入路由，保持注册顺序 | ✅ |
| `folder_zip.py` | 路由 | `POST /import/folder` · `POST /import/zip` | ✅ |
| `obsidian.py` | 路由 | `POST /import/obsidian` · `POST /import/obsidian-zip` 与 vault 遍历 | ✅ |

## 依赖关系

- 各模块无横向依赖，全部通过 `__init__.py` 聚合。
