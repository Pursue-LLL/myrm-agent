# toolkits/kanban/types/

## 架构概述

看板领域值对象：枚举、metadata 约定与数据模型分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 导出全部类型、枚举、派生集合与 metadata 助手 |
| `enums.py` | 任务状态、阻塞类型、优先级、运行/事件/执行结果枚举与派生集合 |
| `metadata.py` | 来源会话与完成意图的 metadata 键与读写 |
| `models.py` | 看板、任务、依赖边、声明、运行、事件与执行结果 |
