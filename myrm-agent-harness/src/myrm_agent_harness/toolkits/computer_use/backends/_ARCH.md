# backends/

## Overview
Platform-specific implementations of the ComputerBackend protocol. Provides macOS, Windows, and Linux desktop automation backends, with optional background-input support via `cua-driver`.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Computer use backends — re-exports ComputerBackend protocol. | — |
| protocols.py | Core | ComputerBackend protocol — abstract interface for platform backends. | ✅ |
| macos.py | Core | macOS backend — screencapture + Quartz CGEvent + NSScreen DPI + AX text; window-targeted capture (`screencapture -l`) and foreground guard via `macos_background`, `check_permissions` via `macos_permissions`; `set_excluded_capture_window_titles` 帷幕排除通道注入；帷幕在屏时全局 HID 坐标类指针动作（click/mouse_move/scroll/drag）fail-closed（`_pointer_occluded`，定向投递与键盘不受影响）. | ✅ |
| macos_input.py | Core | macOS input primitives — Quartz CGEvent keyboard/mouse (replaces pyautogui); PID-targeted delivery via single post router; `has_input_target()` 判定当前任务是否定向投递. | ✅ |
| macos_pasteboard.py | Core | macOS 剪贴板借用原语 — `snapshot` 读取全部 item 的全部类型、`write_text` 写临时文本（总带 `TransientType`，凭证再带 `ConcealedType`，失败抛 `RuntimeError`）、`restore` 以 `changeCount` 守卫还原（用户在粘贴期间新复制则放弃）；`paste_text` 在一个同步函数里完成快照、写入、按键回调、等待、`finally` 还原，模块锁串行重叠调用（`macos.py:_paste_text` 只用一次 `to_thread` 调用它）；AppKit 调用期惰性导入. | ✅ |
| macos_background.py | Core | macOS background ops — window resolve, `screencapture -l` capture, foreground guard, post-event permission, EnhancedUI (crash-contained probe); `_capture_screen_excluding_titles` Quartz below-window 截图通道（帷幕窗排除，失败降级原 screencapture 路径）. | ✅ |
| macos_ax_scripts.py | Core | macOS accessibility probe scripts — AppleScript sources (`AX_TEXT_SCRIPT` window text, `AX_DIALOG_SCRIPT` blocking dialog) consumed by `macos.py`; parsing and timeouts stay with the callers. | — |
| macos_permissions.py | Core | macOS TCC permission probes — Accessibility (`AXIsProcessTrusted` + osascript capability probe), Screen Recording (`CGPreflightScreenCaptureAccess`), optional capture-usability probe, post-event access, System Settings deeplinks (`_MACOS_DEEPLINKS`, also consumed by `perception/macos_ax.py`); consumed by `macos.py` `check_permissions`. | ✅ |
| windows.py | Core | Windows backend — mss + pyautogui + ctypes/user32 + uiautomation; `set_excluded_capture_window_titles` 帷幕排除注入；帷幕在屏时全局指针动作 fail-closed（`_pointer_occluded`）；全屏截图合并 `SNAPSHOT_ONLY_EXCLUDED_CAPTURE_TITLES`（视觉审批高亮）. | ✅ |
| windows_text_io.py | Core | Windows 文本桥 — `type_unicode_text`（`SendInput` Unicode 键事件逐 UTF-16 代码单元输入，换行折成一次 Return，分块发送，不碰剪贴板；UIPI 拦截不可检测）、`extract_window_text`（uiautomation 前台窗口文本，递归收集有深度/数量上限）；Win32 与 uiautomation 调用期解析，跨平台可导入. | ✅ |
| windows_background.py | Core | Windows overlay ops — `_lowest_overlay_hwnd` title 探测；`_capture_screen_excluding_titles` mss 路径（帷幕 WDA 已由桌面端设置）. | ✅ |
| linux.py | Core | Linux backend — scrot/gnome-screenshot + xdotool + DISPLAY auto-detection；`_run_cmd` 不经 shell（`create_subprocess_exec`，命令串只 `shlex.split` 一次），显示器编号与固定的 `LC_ALL=C.UTF-8` 经 `env` 传入（xdotool 按 locale 解码，非 UTF-8 时遇到首个非 ASCII 字符即中断；LC_ALL 优先级高于 LC_CTYPE，宿主设了 LC_ALL=C 也能覆盖），缺工具回 127，超时杀进程回 124，调用被取消时杀掉子进程；输入命令经 `_run_input` 校验退出码（缺工具即失败）；`type_text` / `type_credential` 交给 `X11TextInput`；`screen_context` / 分辨率探测同一 `env`；`key` 的按键串经 `shlex.join` 引用后才成为 xdotool 参数. | ✅ |
| linux_text_io.py | Core | Linux X11 文本输入 — `X11TextInput.enter`：纯 ASCII 经 stdin 交给 `xdotool type --delay N --file -`（分块，不进命令行参数，不碰剪贴板）；含任何非 ASCII 字符的文本整段走 xclip + Ctrl+V 粘贴（xdotool 逐字符重映射键码，真实应用会丢字、串字），粘贴前读原剪贴板（3 秒超时防所有者卡死），`finally` 写回原内容（原为空也写回空串，凭据不残留），实例级锁串行重叠粘贴；ASCII 分块失败报「typed N of M characters」；命令运行器由后端注入. | ✅ |
| linux_probes.py | Core | Linux 屏幕只读探测 — `probe_linux_capturable`（scrot / gnome-screenshot 实截一张并判定可用）、`detect_linux_resolution`（xdpyinfo / xrandr，读不到回退 1920x1080）；仅被 `linux.py` 引用. | ✅ |
| cua_driver.py | Enhancement | Background-input backend via cua-driver MCP. Wraps a native backend. | ✅ |
| cua_driver_spawn.py | Enhancement | MCP stdio argv policy — ``--no-overlay`` defaults and ``--help`` capability probe. | ✅ |

Desktop backends cover macOS / Windows / Linux only.

## Backend Selection (session.py → create_computer_session)

```
All platforms (macOS / Windows / Linux):
  cua-driver installed? ─── YES ──→ CuaDriverBackend(fallback=NativeBackend)
                        └── NO  ──→ NativeBackend (macOS: Quartz CGEvent / Windows: pyautogui / Linux: xdotool)
```

## cua-driver Integration

`CuaDriverBackend` uses the **proxy pattern**: input operations (click, type, key, scroll, drag, mouse_move) are routed to `cua-driver` via MCP stdio for background (focus-free) execution. Non-input operations (screenshot, screen_info, window_text, etc.) are delegated to the platform-native fallback backend.

If cua-driver fails for any individual action, it transparently falls back to the native backend for that operation. If cua-driver is not installed, it is never loaded.

**Install cua-driver**: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.sh)"`

## Key Dependencies

- `mss` (Windows screenshot capture)
- `pyobjc-framework-Quartz` (macOS input simulation — native CGEvent, avoids rubicon-objc arm64 bug)
- `pyautogui` (Windows input simulation — native fallback)
- `uiautomation` (Windows accessibility text extraction, optional)
- `xdotool` (Linux input simulation)
- `cua-driver` (macOS/Windows/Linux background input, optional, MIT license)
- `mcp` (Python MCP SDK, required only when cua-driver is used)
- `computer_use.capture_probe` + Pillow (optional decode) when `probe_capture=True`

## check_permissions() Protocol

All backends implement `check_permissions(*, probe_capture: bool = False) -> PermissionStatus`.

- **Default (`probe_capture=False`)**: OS grant signals only (`accessibility`, `screen_recording`).
  `screen_recording_capturable` stays `None`. `all_granted` ignores capturable.
- **`probe_capture=True`**: After grants, take a short capture sample and set
  `screen_recording_capturable` via shared `computer_use/capture_probe.py`
  (`png_bytes_look_capturable`). Doctor and FE Recheck use this path.
  `PermissionStatus.capture_ready` is True only when grants OK **and** capturable is True.
- Missing Pillow → capturable False (cannot verify; never fake ready).

| Platform | Accessibility Check | Screen Recording Check | Capture sample (when probing) |
|----------|-------------------|----------------------|-------------------------------|
| **macOS** | `AXIsProcessTrusted()` via ctypes **+ osascript** frontmost-process capability probe (osascript is a separate TCC binary) | `CGPreflightScreenCaptureAccess` via ctypes | `screencapture` PNG → luminance gate |
| **Windows** | Always granted (no TCC) | Always granted (no TCC) | mss/GDI PNG → luminance gate; deeplinks are OS/docs URLs only |
| **Linux** | Always granted (no per-app TCC) | Always granted | scrot/gnome-screenshot PNG → luminance gate |

macOS returns `settings_deeplinks` with `x-apple.systempreferences:` URLs for System Settings → Privacy & Security.
