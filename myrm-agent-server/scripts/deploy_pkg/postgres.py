import subprocess
import time

from .checks import check_postgres_installed
from .constants import POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER
from .utils import command_exists, get_os_type, print_error, print_info, print_success, run_command


def install_postgres_macos() -> bool:
    """在 macOS 上安装 PostgreSQL"""
    print_info("正在安装 PostgreSQL (macOS)...")

    if not command_exists("brew"):
        print_error("需要 Homebrew 来安装 PostgreSQL")
        print_info("安装 Homebrew: https://brew.sh/")
        return False

    try:
        run_command(["brew", "install", "postgresql@16"])
        run_command(["brew", "services", "start", "postgresql@16"])
        print_success("PostgreSQL 安装成功")
        print_info("等待 PostgreSQL 启动...")
        time.sleep(3)
        return True
    except Exception as e:
        print_error(f"PostgreSQL 安装失败: {e}")
        return False

def install_postgres_linux() -> bool:
    """在 Linux 上安装 PostgreSQL"""
    print_info("正在安装 PostgreSQL (Linux)...")

    try:
        run_command(["sudo", "apt-get", "update"])
        run_command(["sudo", "apt-get", "install", "-y", "postgresql", "postgresql-contrib"])
        run_command(["sudo", "systemctl", "start", "postgresql"])
        run_command(["sudo", "systemctl", "enable", "postgresql"])
        print_success("PostgreSQL 安装成功")
        return True
    except Exception as e:
        print_error(f"PostgreSQL 安装失败: {e}")
        print_info("请手动安装 PostgreSQL")
        return False

def install_postgres_windows() -> bool:
    """在 Windows 上安装 PostgreSQL"""
    print_info("Windows 需要手动安装 PostgreSQL")
    print_info("下载地址: https://www.postgresql.org/download/windows/")
    print_info("或使用: winget install PostgreSQL.PostgreSQL")
    return False

def install_postgres() -> bool:
    """安装 PostgreSQL"""
    if check_postgres_installed():
        print_success("PostgreSQL 已安装")
        return True

    os_type = get_os_type()

    if os_type == "macos":
        return install_postgres_macos()
    elif os_type == "linux":
        return install_postgres_linux()
    elif os_type == "windows":
        return install_postgres_windows()
    else:
        print_error(f"不支持的操作系统: {os_type}")
        return False

def _run_postgres_command(sql: str, os_type: str, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
    """执行 PostgreSQL 命令（处理 macOS/Linux 差异）"""
    base_cmd = ["psql", "postgres"]
    if os_type == "linux":
        base_cmd = ["sudo", "-u", "postgres"] + base_cmd

    return run_command(base_cmd + ["-c" if not capture else "-tc", sql], capture=capture, check=check)

def init_postgres_database() -> bool:
    """初始化 PostgreSQL 数据库"""
    print_info("正在初始化数据库...")
    os_type = get_os_type()

    if os_type not in ("macos", "linux"):
        print_error(f"不支持的操作系统: {os_type}")
        return False

    try:
        # 检查并创建用户
        result = _run_postgres_command(
            f"SELECT 1 FROM pg_roles WHERE rolname='{POSTGRES_USER}'",
            os_type,
            capture=True,
            check=False,
        )

        if "1" not in (result.stdout or ""):
            _run_postgres_command(
                f"CREATE USER {POSTGRES_USER} WITH PASSWORD '{POSTGRES_PASSWORD}' CREATEDB;",
                os_type,
            )
            print_success(f"创建用户: {POSTGRES_USER}")

        # 检查并创建数据库
        result = _run_postgres_command(
            f"SELECT 1 FROM pg_database WHERE datname='{POSTGRES_DB}'",
            os_type,
            capture=True,
            check=False,
        )

        if "1" not in (result.stdout or ""):
            _run_postgres_command(
                f"CREATE DATABASE {POSTGRES_DB} OWNER {POSTGRES_USER};",
                os_type,
            )
            print_success(f"创建数据库: {POSTGRES_DB}")

        print_success("数据库初始化完成")
        return True

    except Exception as e:
        print_error(f"数据库初始化失败: {e}")
        return False

