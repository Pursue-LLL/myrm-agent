"""
@input: 依赖 app.core.infra.health 的「健康检查引擎」
@output: 对外提供启动前资源健康检查与自动恢复
@pos: 启动健康检查 —— 确保基础设施资源可用

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

import os


def run_startup_health_check(
    skip_health_check: bool = False,
    auto_recovery: bool = True,
    force_recovery: bool = False,
) -> None:
    """Run health checks before starting the server.

    Args:
        skip_health_check: Skip health checks entirely
        auto_recovery: Enable automatic recovery on failure
        force_recovery: Allow dangerous recovery actions (SQLite WAL deletion)
    """
    if skip_health_check or os.getenv("SKIP_HEALTH_CHECK", "").lower() == "true":
        print("[Health] Health checks skipped (--skip-health-check or SKIP_HEALTH_CHECK=true)")
        return

    import asyncio

    from app.core.infra.health import run_all_health_checks

    print("[Health] Running startup health checks...")

    try:
        all_healthy, results = asyncio.run(
            run_all_health_checks(
                auto_recover=auto_recovery,
                force_sqlite_wal_cleanup=force_recovery,
                max_retries=1,
            )
        )

        if not all_healthy:
            print("\n⚠️  Warning: Some health checks failed")
            print("    Review the logs above for details")
            print("    Server will attempt to start, but may encounter issues\n")

    except Exception as e:
        print(f"\n❌ Health check error: {e}")
        import traceback

        traceback.print_exc()
        print("    Server will attempt to start anyway\n")

    print()  # Add blank line for readability
