"""关闭期租约交还的接线守护 — 回锁必须排在耗时的 drain 之前。

[INPUT]
- app/server/lifespan.py（POS: 服务关闭编排；以 AST 读取，不导入整个应用）

[OUTPUT]
- `_shutdown` 先 await stop_unattended_curtain_watcher、再 begin_drain 的顺序断言

[POS]
桌面壳优雅停机只等 server 自退 5s（python_backend_stop.rs），超时即强杀进程树，
且壳退出时帷幕窗口一并消失。回锁若排在可能耗时的 drain 之后，就可能永远轮不到执行，
屏幕以解锁态裸露。行为本身由 test_unattended_lease.py 覆盖，本文件只钉住调用顺序。
"""

from __future__ import annotations

import ast
from pathlib import Path

_LIFESPAN = Path(__file__).resolve().parents[3] / "app" / "server" / "lifespan.py"


def _awaited_call_lines(function: ast.AsyncFunctionDef) -> dict[str, int]:
    """函数体内每个被 await 的调用名 → 首次出现的行号（属性调用取属性名）。"""
    first_line: dict[str, int] = {}
    for node in ast.walk(function):
        if not isinstance(node, ast.Await) or not isinstance(node.value, ast.Call):
            continue
        target = node.value.func
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        first_line.setdefault(name, node.lineno)
    return first_line


def test_shutdown_hands_the_lease_back_before_the_slow_drain() -> None:
    module = ast.parse(_LIFESPAN.read_text(encoding="utf-8"))
    shutdown = next(node for node in module.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "_shutdown")

    awaited = _awaited_call_lines(shutdown)

    assert "stop_unattended_curtain_watcher" in awaited, "_shutdown must hand the unlock lease back"
    assert "begin_drain" in awaited
    assert awaited["stop_unattended_curtain_watcher"] < awaited["begin_drain"]
