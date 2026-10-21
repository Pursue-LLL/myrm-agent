"""
@input: 无外部依赖，纯环境变量与文件系统操作
@output: 对外提供分层 .env 加载、__pycache__ 清理、浏览器路径设置
@pos: 启动环境加载器 —— 最先执行的初始化逻辑

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

import logging
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv


class _UnclosedSessionFilter(logging.Filter):
    """Suppress 'Unclosed client session' from third-party libs (aiohttp GC noise)."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "Unclosed client session" not in record.getMessage()


logging.getLogger("asyncio").addFilter(_UnclosedSessionFilter())


def load_env_files() -> None:
    """分层加载 .env 配置（后加载的覆盖先加载的）。

    加载顺序：
    1. .env（进程级配置）
    2. .env.local 或 .env.sandbox（根据 DEPLOY_MODE 选择）
    3. .env.local（本地开发覆盖，如果存在）

    [T] 测试密钥仅由 ``tests/conftest.py`` → ``tests/support/test_secrets.py`` 加载，server 启动不读取 ``.env.test``。
    """
    # 1. 加载通用基础配置
    load_dotenv(override=False)

    # 2. 根据 DEPLOY_MODE 加载对应的部署模式配置
    from app.config.deploy_mode import DeployMode, get_deploy_mode

    deploy_mode = get_deploy_mode()
    if deploy_mode == DeployMode.LOCAL:
        env_local = Path(".env.local")
        if env_local.exists():
            load_dotenv(env_local, override=False)
    elif deploy_mode == DeployMode.SANDBOX:
        env_mode_file = Path(".env.sandbox")
        if env_mode_file.exists():
            load_dotenv(env_mode_file, override=False)

    # 3. 加载本地开发覆盖配置（如果存在）
    env_local_file = Path(".env.local")
    if env_local_file.exists():
        load_dotenv(env_local_file, override=False)


def clean_pycache() -> None:
    """清理 app/ 下所有 __pycache__ 目录，防止旧 .pyc 与源码不一致导致幽灵 bug。"""
    # __file__ = .../myrm-agent-server/app/startup/env_loader.py
    # parent.parent = .../myrm-agent-server/app/
    app_root = Path(__file__).resolve().parent.parent
    for pyc_dir in app_root.rglob("__pycache__"):
        shutil.rmtree(pyc_dir, ignore_errors=True)


def setup_browser_path() -> None:
    """Set Patchright/Playwright browser binary search path.

    When a local myrm-agent-harness checkout exists, sets PLAYWRIGHT_BROWSERS_PATH
    to harness/.browsers. Otherwise leaves the env unset (Playwright/Patchright defaults).
    PATCHRIGHT_BROWSERS_PATH is NOT overwritten here.
    """
    # __file__ = .../myrm-agent-server/app/startup/env_loader.py
    # parent.parent.parent.parent = myrm-agent/ (产品仓根，与 myrm-agent-server 同级)
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    harness_browsers = project_root / "myrm-agent-harness" / ".browsers"
    if harness_browsers.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(harness_browsers)


def init_environment() -> None:
    """执行所有环境初始化（按顺序）。"""
    load_env_files()
    clean_pycache()
    setup_browser_path()
