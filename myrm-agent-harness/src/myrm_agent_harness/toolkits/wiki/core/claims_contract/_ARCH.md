# wiki/core/claims_contract/

## 架构概述

claim/evidence frontmatter 契约：模型、解析、证据快照与元数据血缘分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 导出模型、解析、快照与血缘函数 |
| `models.py` | WikiEvidence / WikiClaim / 状态常量的模型层 |
| `parsing.py` | frontmatter 解析、校验、合并与降级 claims |
| `snapshots.py` | 证据摘录、快照哈希、raw 字节 LRU、编译前置与修复 |
| `lineage.py` | metadata 读写、resource URI、raw_supersede 血缘 |
