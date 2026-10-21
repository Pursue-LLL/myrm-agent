import subprocess
import sys

from .utils import command_exists, print_error, print_info, print_success, print_warning, run_command


def check_python_version() -> bool:
    """检查 Python 版本"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 11:
        print_success(f"Python 版本: {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_error(f"Python 版本过低: {version.major}.{version.minor}.{version.micro}")
        print_info("需要 Python 3.11 或更高版本")
        return False


def check_uv_installed() -> bool:
    """检查 uv 是否安装"""
    if command_exists("uv"):
        print_success("uv 已安装")
        return True
    else:
        print_warning("uv 未安装")
        print_info("正在安装 uv...")
        try:
            run_command(["pip", "install", "uv"])
            print_success("uv 安装成功")
            return True
        except Exception as e:
            print_error(f"uv 安装失败: {e}")
            print_info("请手动安装: pip install uv")
            return False


def check_docker_installed() -> bool:
    """检查 Docker 是否安装并运行"""
    if command_exists("docker"):
        try:
            run_command(["docker", "info"], capture=True)
            print_success("Docker 已安装并运行")
            return True
        except subprocess.CalledProcessError:
            print_error("Docker 已安装但未运行")
            print_info("请启动 Docker Desktop 或 Docker 服务")
            return False
    else:
        print_error("Docker 未安装")
        print_info("请安装 Docker: https://docs.docker.com/get-docker/")
        return False


def check_postgres_installed() -> bool:
    """检查 PostgreSQL 是否安装"""
    return command_exists("psql")
