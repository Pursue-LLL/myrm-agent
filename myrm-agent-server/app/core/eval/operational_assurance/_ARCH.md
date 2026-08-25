# app/core/eval/operational_assurance 模块架构

---

## 架构概述

`operational_assurance` 属于 `app/core/eval` 模块下的企业级运行保障审计基准适配器。它提供了一个无需网络下载的离线基准套件（`operational-assurance`），覆盖 6 大企业级故障排查与自愈场景（权限拒绝、工具超时、发布/会话恢复、沙箱枯竭、Skill 冲突、证据过期）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 包对外门面导出。 |
| `adapter.py` | 框架 `BenchmarkSpec` 注册与用例转换适配。 |
| `fixtures.py` | 确定性评测用例构造与种子工作区生成。 |
