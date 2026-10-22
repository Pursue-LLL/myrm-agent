# services/artifacts/delight_showcase 模块架构

---

## 架构概述

小白零门槛趣味创意灵感工坊与单文件自包含即席沙箱展示台服务（Item 40 P0）。
预置生活/庆祝/浪漫/趣味工具类单文件 HTML5/Canvas 高质量脚手架，并提供面向小白与家庭场景的单文件自包含规范化与沙箱契约服务。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `catalog.py` | 数据 | 预置 8+ 套生活趣味、节日庆祝、游戏与生成艺术单文件完整自包含 HTML 模板 |
| `service.py` | 核心 | `DelightShowcaseService` 单例服务，承载模板分类检索、模糊搜索与单文件沙箱有效性校验编译 |
| `__init__.py` | 门面 | 导出 `DelightShowcaseService` |
| `_ARCH.md` | 文档 | 模块架构描述与文件清单 |

---

## 依赖关系

- `myrm_agent_harness.toolkits.artifacts.delight_showcase`
