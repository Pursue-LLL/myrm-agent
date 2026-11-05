# cron/blueprints/i18n/

## 架构概述

蓝图的 ja/de/ko 补充文案：en/zh 文案写在蓝图定义里，本包只放其余三种语言的标题、描述与提示词模板，按蓝图 ID 索引。`core/types.py` 的 `_with_supplemental_locales` 用 `SUPPLEMENTAL_BY_ID` 按蓝图 ID 取补充文案，逐字段合并进蓝图（同语言键以补充文案为准）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 按 daily、finance、knowledge、growth 的顺序合并四个分组的 `SUPPLEMENTAL_BY_ID`，并导出 `BLUEPRINT_UI_LOCALES`、`BlueprintLocaleSupplement` | ✅ |
| `types.py` | 类型 | `BlueprintLocaleSupplement`（`title` / `description` / `prompt_template` 三个按语言索引的字典）与 `BLUEPRINT_UI_LOCALES`（`en`、`zh`、`ja`、`de`、`ko`） | ✅ |
| `daily.py` | 数据 | daily 组蓝图的补充文案 | ✅ |
| `finance.py` | 数据 | finance 组蓝图的补充文案 | ✅ |
| `knowledge.py` | 数据 | knowledge 组蓝图的补充文案 | ✅ |
| `growth.py` | 数据 | growth 组蓝图的补充文案 | ✅ |

## 依赖

- 分组模块只依赖 `types.py`，彼此不引用
- 分组间出现同一蓝图 ID 时，合并顺序靠后的分组覆盖靠前的
