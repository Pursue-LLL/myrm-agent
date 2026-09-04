"""Growth subpackage — skill growth case queries, audit, projection, and lifecycle.

[POS]
技能成长子域。constants 为动作类型 SSOT，case_types 为 DTO，
queries 为成长 case 查询，audit_queries 为账本审计，projection_queries 为账本投影，
lifecycle 为成长编排入口，proxy_guard 为自进化代理指标对齐守卫（Goodhart 防护）。

[IMPORT CONSTRAINT]
外部消费者一律穿透导入子模块（如 ``app.services.skills.growth.queries``）。
本包与 ``evolution_review/`` 不做聚合导出——若两包同时聚合，``experience_ledger →
本包 → evolution_reviews → evolution_review.* → experience_ledger`` 构成循环导入。
"""
