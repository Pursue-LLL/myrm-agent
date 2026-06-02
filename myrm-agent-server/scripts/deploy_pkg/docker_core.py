import time
from pathlib import Path

from .checks import check_docker_installed, check_python_version, check_uv_installed
from .constants import ENV_DEFAULTS, ENV_FILE, ENV_LOCAL, ENV_SECRETS, ENV_SECRETS_EXAMPLE, POSTGRES_USER
from .utils import merge_env_files, print_error, print_header, print_info, print_step, print_success, print_warning, run_command


def _deploy_with_docker_compose(
    profiles: list[str],
    env_file: Path,
    mode_name: str,
    services_info: list[str],
) -> bool:
    """使用 Docker Compose 部署服务的通用流程

    执行步骤：
    1. 检查 Docker 环境
    2. 检查 Python 和 uv
    3. 合并环境变量文件
    4. 启动 Docker Compose 服务
    5. 等待服务就绪（PostgreSQL）
    6. 安装 Python 依赖

    Args:
        profiles: Docker Compose profiles 列表（如 ['storage', 'graph']）
        env_file: 模式专用环境变量文件路径（如 .env.sandbox）
        mode_name: 模式名称（用于日志输出）
        services_info: 服务信息列表（用于最终输出）

    Returns:
        部署是否成功
    """
    step = 0

    # Step 1: 检查 Docker
    step += 1
    print_step(step, "检查 Docker")
    if not check_docker_installed():
        return False

    # Step 2: 检查 Python 和 uv
    step += 1
    print_step(step, "检查 Python 环境")
    if not check_python_version():
        return False
    if not check_uv_installed():
        return False

    # Step 3: 复制配置文件
    step += 1
    print_step(step, "配置环境变量")

    # 检查是否有 .env.secrets
    if not ENV_SECRETS.exists() and ENV_SECRETS_EXAMPLE.exists():
        print_warning(".env.secrets 不存在")
        print_info("请复制 .env.secrets.example 为 .env.secrets 并填写敏感信息")

    # 合并配置文件：defaults -> mode-specific -> secrets
    config_files = [ENV_DEFAULTS, env_file, ENV_SECRETS]
    merge_env_files(config_files, ENV_FILE)

    # Step 4: 启动 Docker 服务
    step += 1
    print_step(step, "启动 Docker 服务")

    try:
        cmd = ["docker", "compose"]
        for profile in profiles:
            cmd.extend(["--profile", profile])
        cmd.extend(["up", "-d"])

        run_command(cmd)
        print_success("Docker 服务启动成功")
    except Exception as e:
        print_error(f"Docker 服务启动失败: {e}")
        return False

    # Step 5: 等待服务就绪
    step += 1
    print_step(step, "等待服务就绪")

    print_info("等待 PostgreSQL 启动...")
    time.sleep(5)

    for _ in range(30):
        try:
            result = run_command(
                ["docker", "exec", "postgres", "pg_isready", "-U", POSTGRES_USER],
                capture=True,
                check=False,
            )
            if result.returncode == 0:
                print_success("PostgreSQL 已就绪")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        print_warning("PostgreSQL 启动超时，请检查 docker compose logs postgres")

    # Step 6: 安装依赖
    step += 1
    print_step(step, "安装 Python 依赖")
    try:
        run_command(["uv", "sync", "--all-extras"])
        print_success("依赖安装完成")
    except Exception as e:
        print_error(f"依赖安装失败: {e}")
        return False

    # 完成
    print_header("部署完成！")
    print_success(f"{mode_name} 部署成功")
    print()
    print("已启动的服务:")
    for service in services_info:
        print(f"  {service}")
    print()
    print("💡 提示: Docker 模式使用 Qdrant Server，支持多进程并发，无文件锁冲突")
    print()

    return True

def deploy_docker() -> bool:
    """Docker 一键全栈部署（后端 + 前端）

    使用 docker compose --profile app 启动完整应用栈。
    后端使用 SQLite + Qdrant Embedded，无需外部数据库。
    适用于非开发者用户快速体验、Demo 演示、CI/CD 测试等场景。
    """
    print_header("MyrmAgent - Docker 全栈部署")
    print_info("此模式将后端 + 前端 Docker 化部署（SQLite，无外部数据库依赖）")
    print()

    step = 0

    # Step 1: 检查 Docker
    step += 1
    print_step(step, "检查 Docker")
    if not check_docker_installed():
        return False

    # Step 2: 配置环境变量
    step += 1
    print_step(step, "配置环境变量")

    if not ENV_LOCAL.exists():
        print_info("使用默认配置")
        config_files = [ENV_DEFAULTS]
    else:
        config_files = [ENV_DEFAULTS, ENV_LOCAL]

    if ENV_SECRETS.exists():
        config_files.append(ENV_SECRETS)

    merge_env_files(config_files, ENV_FILE)

    # Step 3: 构建并启动
    step += 1
    print_step(step, "构建并启动 Docker 服务")

    try:
        cmd = ["docker", "compose", "--profile", "app", "--profile", "search", "up", "-d", "--build"]
        run_command(cmd)
        print_success("Docker 服务启动成功")
    except Exception as e:
        print_error(f"Docker 服务启动失败: {e}")
        return False

    # Step 4: 等待服务就绪
    step += 1
    print_step(step, "等待服务就绪")

    print_info("等待后端启动...")
    for _ in range(60):
        try:
            result = run_command(
                ["docker", "exec", "myrm-backend", "curl", "-sf", "http://localhost:25808/health"],
                capture=True,
                check=False,
            )
            if result.returncode == 0:
                print_success("后端已就绪")
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        print_warning("后端启动超时，请检查: docker compose logs backend")

    print_header("部署完成！")
    print_success("Docker 全栈部署成功")
    print()
    print("已启动的服务:")
    print("  - 前端:     http://localhost:3000")
    print("  - 后端 API: http://localhost:25808")
    print("  - 数据库:   SQLite（容器内 /home/myrm/.myrm/）")
    print()
    print("💡 提示:")
    print("  查看日志:  docker compose logs -f")
    print("  停止服务:  docker compose --profile app down")
    print()

    return True

