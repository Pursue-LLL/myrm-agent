"""
@input: 依赖 app.config.settings 的「全局配置」，依赖 psutil 外部库
@output: 对外提供 OS 级文件锁获取与僵尸进程猎杀
@pos: 服务器进程锁管理 —— 确保单实例运行，支持无感重启

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

import os
import sys
from pathlib import Path

import psutil

from app.config.settings import settings

_state_dir = Path(settings.database.state_dir)
_server_lock = None


def acquire_server_lock(target_port: int, target_host: str = "0.0.0.0") -> None:
    """获取 OS 原子锁，避免多开冲突。若检测到遗留进程则尝试无感接管。"""
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

    def _find_pid_by_port(port: int) -> int | None:
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr.port == port and conn.status == "LISTEN":
                    pid = conn.pid
                    if pid:
                        try:
                            proc = psutil.Process(pid)
                            parent = proc.parent()
                            if parent:
                                p_cmd = " ".join(parent.cmdline()).lower()
                                if "run.py" in p_cmd or "myrm-agent" in p_cmd or "granian" in p_cmd:
                                    return parent.pid
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        return pid
        except (psutil.AccessDenied, Exception):
            pass
        return None

    def _find_pids_by_scan() -> set[int]:
        pids: set[int] = set()
        try:
            workspace_path = str(Path(__file__).resolve().parents[2])
            for proc in psutil.process_iter(["pid", "cmdline", "status", "cwd"]):
                if proc.info["status"] == psutil.STATUS_ZOMBIE:
                    continue

                # 排除当前进程自身及其祖先进程
                try:
                    current_proc = psutil.Process(os.getpid())
                    ancestors = [p.pid for p in current_proc.parents()]
                    if proc.info["pid"] == os.getpid() or proc.info["pid"] in ancestors:
                        continue
                except Exception:
                    if proc.info["pid"] == os.getpid():
                        continue

                cmdline = proc.info.get("cmdline")
                if not cmdline:
                    continue
                cmd_str = " ".join(cmdline).lower()

                # 严格指纹匹配，包括孤儿 worker
                if "run.py" in cmd_str or "myrm-agent" in cmd_str or "granian" in cmd_str or "app.main" in cmd_str:
                    # 工作区级严格指纹锁定
                    is_match = False
                    try:
                        cwd = proc.info.get("cwd")
                        if cwd and cwd.startswith(workspace_path):
                            is_match = True
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        pass

                    if not is_match and workspace_path.lower() in cmd_str:
                        is_match = True

                    if is_match:
                        pids.add(proc.info["pid"])
        except Exception:
            pass
        return pids

    try:
        _server_lock.acquire()
        _write_pid_atomic()
    except Timeout:
        # 锁被占用，尝试智能猎杀僵尸进程以实现无感重启
        try:
            target_pids: set[int] = set()

            # Tier 1: 读取 PID 文件
            if pid_file.exists():
                try:
                    with open(pid_file, "r") as f:
                        content = f.read().strip()
                        if content:
                            old_pid = int(content)
                            if psutil.pid_exists(old_pid):
                                target_pids.add(old_pid)
                except Exception:
                    pass

            # Tier 2: 跨平台物理降级（通过端口反查）
            port_pid = _find_pid_by_port(target_port)
            if port_pid and psutil.pid_exists(port_pid):
                target_pids.add(port_pid)

            # Tier 3: 全量指纹扫描（始终执行，捕获绑定不同地址的遗留进程）
            target_pids.update(_find_pids_by_scan())

            if target_pids:
                print(f"⚠️  检测到遗留的后台进程 (PIDs: {list(target_pids)})，正在尝试无感接管...")

                procs_to_kill: list[psutil.Process] = []
                for pid in target_pids:
                    try:
                        if psutil.pid_exists(pid):
                            proc = psutil.Process(pid)
                            if proc.status() != psutil.STATUS_ZOMBIE:
                                procs_to_kill.append(proc)
                                # 连根拔起：预先获取所有子进程
                                try:
                                    for child in proc.children(recursive=True):
                                        if child.status() != psutil.STATUS_ZOMBIE:
                                            procs_to_kill.append(child)
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    pass
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                if procs_to_kill:
                    # 发送 SIGTERM
                    for p in procs_to_kill:
                        try:
                            p.terminate()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

                    # 精确等待
                    gone, alive = psutil.wait_procs(procs_to_kill, timeout=5)

                    if alive:
                        print("⚠️  进程拒绝优雅退出，强制猎杀 (SIGKILL)...")
                        for p in alive:
                            try:
                                p.kill()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                        psutil.wait_procs(alive, timeout=3)

                    # 尝试再次获取锁
                    try:
                        _server_lock.acquire(timeout=1)
                        _write_pid_atomic()

                        # 物理端口释放校验
                        if not _verify_port_free(target_host, target_port):
                            print(f"⚠️  警告：进程已猎杀，但端口 {target_port} 仍未释放 (可能处于 TIME_WAIT)，将继续尝试启动...")
                        else:
                            print("✅  成功接管服务器端口！\n")
                        return
                    except Timeout:
                        pass
        except Exception as e:
            print(f"⚠️  尝试接管进程时发生异常: {e}")

        print(f"❌ 启动失败：服务器进程已经在运行 (锁文件 {lock_file} 被占用)")
        print("💡 OS 级文件锁保证绝对安全。如果您确信没有其他实例，请检查文件权限。")
        print("🔧 正在尝试强制清理遗留锁并重试...")
        try:
            os.remove(lock_file)
            _server_lock.acquire(timeout=1)
            _write_pid_atomic()
            print("✅ 成功清理遗留锁并接管服务器端口！\n")
            return
        except Exception as e:
            print(f"❌ 强制清理锁失败: {e}")
            sys.exit(1)
