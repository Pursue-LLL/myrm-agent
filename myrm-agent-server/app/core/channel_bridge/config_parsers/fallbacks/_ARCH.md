# channel_bridge/config_parsers/fallbacks/

## 架构概述

模型回退链解析：视觉链、视频/槽位链、轻量模型与后台进化模型。`resolution.py` 只解析槽位内的 fallback 项，供视觉与视频两条链共用，避免两模块互相依赖。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出回退链能力 | ✅ |
| `model.py` | 模块 | 轻量模型与视觉回退链 | ✅ |
| `slot.py` | 模块 | 视频、槽位、后台进化回退链 | ✅ |
| `resolution.py` | 模块 | 槽位 fallback 项解析（两条链共用） | ✅ |
