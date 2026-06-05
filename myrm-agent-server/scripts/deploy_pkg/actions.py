import subprocess
import sys

from .checks import check_postgres_installed
from .constants import PROJECT_ROOT
from .utils import command_exists, get_os_type, print_error, print_header, print_info, print_success, print_warning, run_command


def try_start_local_search_profile() -> None:
    """Start SearXNG via docker compose search profile when Docker is available."""
    if not command_exists("docker"):
        print_info("Docker not found — skip auto-starting SearXNG (install Docker or use LiteLLM search in Settings)")
        return
    print_info("Starting SearXNG (docker compose --profile search)...")
    try:
        run_command(["docker", "compose", "--profile", "search", "up", "-d"], check=False)
        print_success("SearXNG profile started (http://127.0.0.1:8081)")
    except Exception as exc:
        print_warning(f"Could not start SearXNG profile: {exc}")


def start_application() -> None:
    """启动应用服务器（调用 run.py 脚本）"""
    print_header("启动应用服务器")
    print_info("调用 run.py 启动应用...")
    print()

    script_path = PROJECT_ROOT / "run.py"
    if not script_path.exists():
        print_error(f"启动脚本不存在: {script_path}")
        print_info("请确保 run.py 文件存在")
        sys.exit(1)

    try:
        # 直接调用脚本，保持环境变量和当前进程状态
        subprocess.run([sys.executable, str(script_path)], check=False)
    except KeyboardInterrupt:
        print("\n📍 Server stopped by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"启动应用失败: {e}")
        sys.exit(1)


def show_status() -> None:
    """显示服务状态"""
    print_header("服务状态")

    # 检查 Docker 服务
    if command_exists("docker"):
        print("\nDocker 服务:")
        try:
            run_command(["docker", "compose", "ps"])
        except Exception:
            print_info("无 Docker 服务运行")

    # 检查本地 PostgreSQL
    print("\n本地 PostgreSQL:")
    if check_postgres_installed():
        os_type = get_os_type()
        if os_type == "macos":
            run_command(["brew", "services", "list"], check=False)
        elif os_type == "linux":
            run_command(["systemctl", "status", "postgresql", "--no-pager"], check=False)
    else:
        print_info("未安装")


def stop_services() -> None:
    """停止所有服务"""
    print_header("停止服务")

    # 停止 Docker 服务
    if command_exists("docker"):
        print("\n停止 Docker 服务...")
        try:
            run_command(
                [
                    "docker",
                    "compose",
                    "--profile",
                    "app",
                    "--profile",
                    "db",
                    "--profile",
                    "search",
                    "--profile",
                    "storage",
                    "down",
                ]
            )
            print_success("Docker 服务已停止")
        except Exception:
            print_info("无 Docker 服务运行")

    print_success("所有服务已停止")
