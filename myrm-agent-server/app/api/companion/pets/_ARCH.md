# api/companion/pets/

## 架构概述

Petdex 宠物的 HTTP 层与伴侣配置里的精灵选择。路由挂在上级 `companion/router.py` 下，共用它的 `companion_mode` feature gate。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口 | — |
| `router.py` | 路由 | `GET /pets`、`POST /pets/install`（装完把它写成当前精灵）、`DELETE /pets/{slug}`（卸载当前精灵时同步清配置）、`GET /pets/{slug}/spritesheet`。 | ✅ |
| `sprite_selection.py` | 模块 | 伴侣配置 `companion_config` 里的精灵选择：写入（`persist_sprite_selection`，保留其他字段）与卸载匹配时清除（`clear_sprite_selection_if_matches`）；路由与旧配置迁移共用。 | ✅ |
