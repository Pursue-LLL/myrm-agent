# services/companion/

## 架构概述

桌宠 **Companion** 业务服务：Observer 反应生成、进化资格查询、Petdex 精灵受管安装（`MYRM_DATA_DIR/companion/pets/`）。与 `mascot/`（XP/状态机）分工见 [../_ARCH.md](../_ARCH.md) 术语表。

HTTP 层：`app/api/companion/`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包标记 | — |
| `pet_store.py` | 核心 | Petdex 宠物受管安装（`MYRM_DATA_DIR/companion/pets/`、manifest 拉取、SHA256、host pinning） | ✅ |
