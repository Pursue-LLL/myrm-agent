from .actions import start_application, try_start_local_search_profile
from .checks import check_python_version, check_uv_installed
from .constants import ENV_DEFAULTS, ENV_FILE, ENV_LOCAL, ENV_SANDBOX
from .docker_core import _deploy_with_docker_compose
from .utils import merge_env_files, print_error, print_header, print_info, print_step, print_success, print_warning, run_command


def deploy_tauri(action: str = "dev") -> bool:
    """Tauri 桌面客户端模式部署

    Args:
        action: dev (开发模式) 或 build (打包)
    """
    print_header("MyrmAgent - Tauri 桌面客户端模式")
    print_info("此模式用于桌面应用，使用本地嵌入式数据库（SQLite + Qdrant 嵌入式）")
    print()

    # 检查 Python 版本
    print_step(1, "检查环境")
    if not check_python_version():
        return False

    if not check_uv_installed():
        return False

    # 配置环境变量
    print_step(2, "配置环境变量")
    if not ENV_LOCAL.exists():
        print_warning(".env.local 不存在，将使用默认配置")
        config_files = [ENV_DEFAULTS]
    else:
        config_files = [ENV_DEFAULTS, ENV_LOCAL]

    merge_env_files(config_files, ENV_FILE)
    print_success("环境变量已配置")

    # 安装依赖
    print_step(3, "安装依赖")
    print_info("安装本地模式依赖（包含 FastEmbed、aiosqlite）...")
    try:
        run_command(["uv", "sync", "--all-extras"])
        print_success("依赖安装完成")
    except Exception as e:
        print_error(f"依赖安装失败: {e}")
        return False

    # 根据 action 执行不同操作
    if action == "dev":
        print_step(4, "启动开发服务器")
        try_start_local_search_profile()
        print_info("开发模式将启动 Python 后端（uvicorn 单进程）")
        print_info("数据存储在: /workspace/")
        print()
        print("📍 服务信息:")
        print("  - 后端 API: http://127.0.0.1:8080")
        print("  - 数据库: SQLite (嵌入式)")
        print("  - 向量库: Qdrant (嵌入式)")
        print("  - 图查询: SQLite 递归 CTE")
        print()
        print("💡 提示: 本地模式使用 uvicorn（单进程），避免嵌入式数据库文件锁冲突")
        print()

        # 启动应用
        start_application()

    elif action == "build":
        print_step(4, "打包 Tauri 应用")
        print_warning("Tauri 打包功能尚未实现")
        print_info("需要先完成 Phase 3: Tauri 集成（Tauri 项目、Sidecar、IPC）")
        return False

    else:
        print_error(f"未知的 action: {action}")
        return False

    return True


def deploy_sandbox() -> bool:
    """沙箱模式部署（使用 Docker）

    特性：
    - 使用 Docker Compose 部署数据库服务（PostgreSQL + AGE、Qdrant、MinIO）
    - 不包含 SearXNG（使用外部搜索 API）
    - 图查询通过 PostgreSQL + Apache AGE 扩展实现
    - 控制平面管理的沙箱实例
    """
    print_header("MyrmAgent - Sandbox Mode")
    print_info("此模式用于沙箱部署，不包含 SearXNG（使用外部搜索 API）")
    print()

    # 配置服务
    print_step(1, "配置服务")
    profiles: list[str] = ["db", "storage"]

    # 选择环境变量文件
    print_step(2, "配置环境变量")
    if not ENV_SANDBOX.exists():
        print_error(".env.sandbox 文件不存在")
        print_info("请创建 .env.sandbox 文件用于沙箱模式配置")
        return False

    env_file = ENV_SANDBOX

    services_info = [
        "- PostgreSQL + AGE: localhost:5432 (关系数据 + 图查询)",
        "- Qdrant: localhost:6333",
        "- MinIO: localhost:9000 (API), localhost:9001 (Console)",
    ]

    success = _deploy_with_docker_compose(
        profiles=profiles,
        env_file=env_file,
        mode_name="Sandbox Mode",
        services_info=services_info,
    )

    if not success:
        return False

    print("⚠️  沙箱模式提醒:")
    print("  - 搜索与 LLM 凭据由 WebUI Settings / CP 注入，不在 .env 中配置")
    print()

    return True
