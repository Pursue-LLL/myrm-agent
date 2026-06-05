"""
@input: 依赖 health_check 的「启动健康检查」，依赖 uvicorn 外部库
@output: 对外提供 uvicorn 单进程启动（含 WebUI 模式、QR 码、浏览器自动打开）
@pos: uvicorn 服务器启动器 —— 默认启动模式

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

import os
import signal
import sys
import webbrowser

from app.config.env import is_debug_mode
from app.startup.health_check import run_startup_health_check


def _uvloop_available() -> bool:
    """Check if uvloop is installed (provides ~2-3x IO performance)."""
    try:
        import uvloop  # noqa: F401

        return True
    except ImportError:
        return False


def _display_qrcode_terminal(url: str) -> None:
    """在终端显示二维码。"""
    try:
        from app.services.webui.qrcode import generate_qrcode_ascii

        print("\n📱 Scan QR Code to access on mobile:\n")
        qr_ascii = generate_qrcode_ascii(url, border=1)
        print(qr_ascii)
        print(f"\nOr visit: {url}\n")
    except ImportError:
        print("\n⚠️  QR code display requires 'qrcode' package")
        print(f"Visit: {url}\n")
    except Exception as e:
        print(f"\n⚠️  Failed to generate QR code: {e}")
        print(f"Visit: {url}\n")


def start_with_uvicorn(
    host: str,
    port: int,
    skip_port_check: bool = False,
    webui_mode: bool = False,
    remote_mode: bool = False,
    no_browser: bool = False,
    no_qrcode: bool = False,
    skip_health_check: bool = False,
    no_auto_recovery: bool = False,
    force_recovery: bool = False,
) -> None:
    """使用 uvicorn 启动（本地单进程模式）。

    Args:
        host: 绑定主机地址
        port: 绑定端口号
        skip_port_check: 是否跳过端口检查
        webui_mode: 是否为 WebUI 模式
        remote_mode: 是否允许远程访问
        no_browser: 是否禁止自动打开浏览器
        no_qrcode: 是否禁止显示二维码
        skip_health_check: 是否跳过健康检查
        no_auto_recovery: 是否禁用自动恢复
        force_recovery: 是否允许危险的恢复操作（SQLite WAL删除）
    """
    # 运行健康检查
    run_startup_health_check(
        skip_health_check=skip_health_check,
        auto_recovery=not no_auto_recovery,
        force_recovery=force_recovery,
    )

    frontend_launcher_instance = None

    if webui_mode:
        frontend_launcher_instance = _setup_webui_mode(
            host,
            port,
            remote_mode,
            no_qrcode,
            no_browser,
        )
    else:
        _print_local_mode_info(host, port)

    force_exit_count = 0

    def _cleanup_frontend() -> None:
        if frontend_launcher_instance:
            frontend_launcher_instance.stop()

    def force_exit_handler(signum: int, frame: object) -> None:
        nonlocal force_exit_count
        force_exit_count += 1
        if force_exit_count >= 2:
            _cleanup_frontend()
            print("\n🛑 强制退出...")
            os._exit(1)
        else:
            print("\n⏳ 正在优雅关闭...再按一次 Ctrl+C 强制退出")
            signal.signal(signal.SIGINT, force_exit_handler)
            raise KeyboardInterrupt()

    try:
        import uvicorn

        from app.main import app

        if frontend_launcher_instance:
            app.state.frontend_launcher = frontend_launcher_instance

        signal.signal(signal.SIGINT, force_exit_handler)

        loop_impl = "uvloop" if _uvloop_available() else "auto"
        uvicorn_log_level = "debug" if is_debug_mode() else "warning"
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=uvicorn_log_level,
            access_log=is_debug_mode(),
            loop=loop_impl,
        )
    except KeyboardInterrupt:
        _cleanup_frontend()
        print("\n📍 Server stopped by user")
        sys.exit(0)
    except ImportError as e:
        _cleanup_frontend()
        print(f"❌ Import Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        _cleanup_frontend()
        print(f"❌ Error starting uvicorn: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def _setup_webui_mode(
    host: str,
    port: int,
    remote_mode: bool,
    no_qrcode: bool,
    no_browser: bool,
) -> object:
    """配置 WebUI 模式：启动前端、显示连接信息、QR 码、打开浏览器。返回 frontend_launcher 或 None。"""
    try:
        from myrm_agent_harness.utils import get_local_ip
    except ImportError:
        print("⚠️  Warning: Failed to import network utils, using fallback")

        def get_local_ip() -> str:  # type: ignore[misc]
            import socket

            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            except Exception:
                return "127.0.0.1"

    local_ip = get_local_ip()
    bind_host = "0.0.0.0" if remote_mode else "127.0.0.1"

    print("=" * 70)
    print("🚀 MyrmAgent - WebUI Mode")
    print("=" * 70)
    print(f"📍 Backend: http://127.0.0.1:{port}")

    # Launch Next.js standalone frontend
    from app.core.infra.frontend_launcher import launch_frontend

    frontend_launcher_instance = launch_frontend(
        api_port=port,
        api_host="127.0.0.1",
        frontend_port=3000,
        bind_host=bind_host,
    )

    if frontend_launcher_instance:
        frontend_url = frontend_launcher_instance.url
        print(f"📍 Frontend: {frontend_url}")
    else:
        frontend_url = f"http://127.0.0.1:{port}/api/v1/webui/welcome"
        print("⚠️  Frontend unavailable, falling back to API-only mode")

    # Remote mode: generate setup token
    setup_token = None
    network_url = ""
    if remote_mode:
        network_url = f"http://{local_ip}:{port}"
        try:
            from app.services.webui.temp_token import temp_token_service

            setup_token = temp_token_service.generate_token()
        except Exception as e:
            print(f"⚠️  Warning: Failed to generate setup token: {e}")

        print(f"🌐 Network: {network_url}")
        print("=" * 70)
        print("🔐 Remote Mode - Authentication Required")
        print("=" * 70)
        if setup_token:
            setup_url = f"{network_url}/auth/setup?token={setup_token}"
            print(f"🔑 Setup URL (valid for 15 minutes): {setup_url}")
        else:
            print(f"🔑 Access: {network_url}")
        print()
        print("⚠️  Security Notice:")
        print("   This server uses HTTP. For remote access over untrusted networks,")
        print("   use a reverse proxy (nginx/Caddy) with HTTPS to encrypt traffic.")
    else:
        print("📍 Local Mode - No authentication required")

    print("=" * 70)
    print("💾 Database: Shared with Desktop mode")
    print("✅ Configurations are synchronized")
    print("=" * 70)

    # QR code display
    if not no_qrcode:
        if remote_mode and setup_token:
            _display_qrcode_terminal(f"{network_url}/auth/setup?token={setup_token}")
        elif remote_mode:
            _display_qrcode_terminal(network_url)
        else:
            _display_qrcode_terminal(frontend_url)

    print()

    # Open browser (pointing to frontend, not backend)
    if not no_browser:
        if remote_mode and setup_token:
            webbrowser.open(f"{frontend_url}/auth/login?token={setup_token}")
        elif remote_mode:
            webbrowser.open(f"{frontend_url}/auth/login")
        else:
            webbrowser.open(frontend_url)

    return frontend_launcher_instance


def _print_local_mode_info(host: str, port: int) -> None:
    """打印本地模式启动信息。"""
    from app.config.deploy_mode import is_webui_mode

    mode_label = "WebUI" if is_webui_mode() else "Local"
    loop_label = "uvloop" if _uvloop_available() else "asyncio"
    print(f"🐍 {mode_label} Mode: uvicorn (single-process, {loop_label})")
    print(f"📍 Starting server at http://{host}:{port}")
