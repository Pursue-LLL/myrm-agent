"""Evolution review subpackage — review lifecycle internals for services.skills.

[POS]
Evolution 审核子域。types 为 DTO/枚举/常量，persistence 为 ApprovalRecord 读写，
queries 为只读查询，actions 为写操作，disk/disk_content 为落盘编排与全量 apply/rollback。

[IMPORT CONSTRAINT]
外部消费者一律穿透导入子模块（如 ``app.services.skills.evolution_review.types``）。
本包与 ``growth/`` 不做聚合导出——若两包同时聚合，``experience_ledger → growth.* →
evolution_reviews → 本包 types → experience_ledger`` 构成循环导入。公共 API 由门面
``../evolution_reviews.py`` 统一 re-export。
"""
