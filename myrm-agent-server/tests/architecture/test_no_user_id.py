"""架构防御测试：确保business layer不包含user_id"""

from app.database.models.base import Base


def test_no_user_id_in_orm_models():
    """确保所有ORM模型不包含user_id字段（除遗留表）"""
    # 允许的遗留表
    allowed_user_id_tables = {
        "user_subscriptions",  # SaaS层表
        "user_quota_usage",  # SaaS层表
        "device_sessions",  # SaaS层表
        "user_pool_skill_refs",  # 遗留表
        "batch_optimization_tasks",  # 遗留表
        "skill_quality_history",  # 遗留表
        "skill_drafts",  # 遗留表
        "failed_messages",  # 遗留表
        "artifact_audit_logs",  # Audit actor id (single-tenant sandbox), not CP multi-tenant
        "commitments",  # Channel-scoped end-user id in single-tenant instance, not CP DB tenant
    }

    for model_class in Base.registry.mappers:
        model = model_class.class_
        table_name = model.__tablename__

        # 跳过允许的遗留表
        if table_name in allowed_user_id_tables:
            continue

        # 检查不应该有user_id字段
        assert not hasattr(model, "user_id"), (
            f"Model {model.__name__} (table: {table_name}) should not have user_id field. "
            f"myrm-agent-server is a single-tenant sandbox layer."
        )
