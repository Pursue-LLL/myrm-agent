# feishu/cards/

## 架构概述

飞书卡片构造：通用卡片、动作、文本与特殊卡片分层，`__init__.py` 保持原 `cards` 导入面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出全部卡片函数 | ✅ |
| `builders.py` | 核心 | 组件/占位与进度/结果卡片与成本备注；结果卡片的来源行按引用编号（`index`，缺省按位置）编号；`CARD_CONFIG` 是渠道所有卡片共用的 config，带 `update_multi`（飞书只原地更新声明了它的卡片） | ✅ |
| `actions.py` | 核心 | 卡片动作按钮构造与回调解析 | ✅ |
| `text.py` | 核心 | 发送模式、富文本/Post | ✅ |
| `special.py` | 核心 | 联系人消歧与交付物卡片 | ✅ |

## 依赖关系

- `builders.py` → `actions.py`
- `special.py` → `builders.py`（共用 `CARD_CONFIG`）
