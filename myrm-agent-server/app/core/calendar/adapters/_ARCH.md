# core/calendar/adapters/

## 架构概述

日历 SQLAlchemy 存储适配器。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Calendar adapters. | ✅ |
| `sqlalchemy_mapping.py` | 模块 | ORM <-> Domain mapping for calendar models. | ✅ |
| `sqlalchemy_store.py` | 模块 | SQLAlchemy implementation of the CalendarStore protocol. | ✅ |
