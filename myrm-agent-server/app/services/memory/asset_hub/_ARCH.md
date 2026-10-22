# asset_hub 模块架构

Agent Memory Asset Hub and Equipment Slots Service.

## 架构概述

提供四大类智能体记忆资产（Chat Memory, Skill, Wiki, CodeGraph）的分类编目、细粒度 ACL 访问控制隔离（Private / Team / Project）、以及游戏化 4 槽位装备栏装配与卸载服务。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `asset_hub_types.py` | 核心模型 | 纯领域模型定义（MemoryAssetType, AclScope, MemoryAsset, EquipmentSlot, AgentEquipmentSummary 等） | ✅ |
| `asset_hub_service.py` | 核心服务 | 四大资产库初始化、ACL 过滤鉴权、槽位类型校验与装配/卸载业务逻辑实现 | ✅ |
| `__init__.py` | 门面 | 导出服务单例与领域模型 | ✅ |
