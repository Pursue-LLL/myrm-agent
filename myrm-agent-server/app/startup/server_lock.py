"""
@input: 依赖 app.config.settings 的「全局配置」，依赖 psutil 外部库
@output: 对外提供 OS 级文件锁获取与僵尸进程猎杀
@pos: 服务器进程锁管理 —— 确保单实例运行，支持无感重启

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

import os
from pathlib import Path

import psutil

from app.config.settings import settings

_state_dir = Path(settings.database.state_dir)
_server_lock = None


def _read_pid_file(pid_file: Path) -> int | None:
    try:
        content = pid_file.read_text(encoding="utf-8").strip()
        return int(content) if content.isdigit() else None
    except (OSError, ValueError):
        return None


def _process_alive(pid: int) -> bool:
    try:
        return (
            psutil.pid_exists(pid)
            and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def acquire_server_lock(target_port: int, target_host: str = "0.0.0.0") -> None:
    """获取 OS 原子锁，保证单实例运行，支持僵尸锁接管。"""
    import socket
    import time

    try:
        from filelock import FileLock, Timeout
    except ImportError:
        print("⚠️  Warning: 'filelock' package not found, skipping OS lock. Run: uv sync")
        return

    global _server_lock
    lock_file = _state_dir / ".server.oslock"
    pid_file = _state_dir / ".server.pid"

    _server_lock = FileLock(str(lock_file), timeout=0)

    def _write_pid_atomic() -> None:
        tmp_pid = pid_file.with_suffix(".pid.tmp")
        with open(tmp_pid, "w") as f:
            f.write(str(os.getpid()))
        os.replace(tmp_pid, pid_file)

    def _verify_port_free(host: str, port: int, timeout: int = 3) -> bool:
        start_time = time.time()
        while time.time() - start_time < timeout:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind((host, port))
                    return True
                except OSError:
                    time.sleep(0.1)
        return False

    try:
        _server_lock.acquire()
        _write_pid_atomic()
    except Timeout:
        # 锁被占用。区分「僵尸锁」（持锁者已死 → 清理接管）与「活跃实例」
        # （另一 backend 正常运行 → 本次启动退出）。
        # 旧实现会全量指纹扫描并猎杀 workspace 内所有 run.py 进程来实现
        # 「无感接管」，但多人开发 / 并行 E2E 下并发启动会互相猎杀——这正是
        # shared backend 反复崩溃的根因（见 BUG-DG-2026-08-09-R010）。
        holder_pid = _read_pid_file(pid_file)
        if holder_pid is not None and _process_alive(holder_pid):
            print(
                f"⚠️  另一 backend 实例正在运行 (pid={holder_pid}, port={target_port})，"
                "本次启动退出，避免互杀。如需重启请先停止旧实例。",
                flush=True,
            )
            # 必须用 os._exit()：sys.exit() 抛 SystemExit 后解释器会等待所有
            # 非 daemon 线程退出，而 run.py 模块导入阶段已创建 libuv 事件循环
            # 等线程，第二实例会被永久卡在 wait_for_thread_shutdown —— 进程
            # 存活但僵尸化，持续占用数据库/端口探测，诱使 supervisor 误判
            # "backend 活着但无响应"（见 BUG-DG-2026-08-09-R014）。
            os._exit(1)

        # 僵尸锁：持锁者已死，清理锁文件并接管（无感重启）。
        try:
            os.remove(lock_file)
        except OSError:
            pass
        try:
            _server_lock.acquire(timeout=1)
            _write_pid_atomic()

            if not _verify_port_free(target_host, target_port):
                print(
                    f"⚠️  警告：端口 {target_port} 尚未释放 (可能处于 TIME_WAIT)，"
                    "将继续尝试启动..."
                )
            else:
                print("✅  成功接管服务器端口！\n")
            return
        except Timeout:
            pass

        print(
            f"❌ 启动失败：服务器进程已经在运行 (锁文件 {lock_file} 被占用)",
            flush=True,
        )
        print("💡 若您确信没有其他实例，请手动删除锁文件后重试。", flush=True)
        os._exit(1)
