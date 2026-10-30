# backends/linux/

## Overview
Linux X11 desktop backend: scrot / gnome-screenshot + xdotool, shell-free command runner, hybrid ASCII-typing / clipboard-paste text input, read-only environment probes.

Linux-only. Loaded by `session.py` when `detect_platform().os_type == "linux"`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Linux 后端包入口（无再导出，调用方按子模块导入）。 | — |
| backend.py | Core | Linux backend — scrot/gnome-screenshot + xdotool + DISPLAY auto-detection；`_run_cmd` 不经 shell（`create_subprocess_exec`，命令串只 `shlex.split` 一次），显示器编号经 `env` 传入，缺工具回 127，超时杀进程回 124，调用被取消时杀掉子进程；输入命令经 `_run_input` 校验退出码（缺工具即失败；xdotool 对未知键名退出 0 但 stderr 报 `No such key name`，同样判失败）；`type_text` 交给 `text_io.py` 的 `X11TextInput`；`screen_context` / 分辨率 / 环境就绪度交给 `probes.py`；`key` 的按键串经 `shlex.join` 引用后才成为 xdotool 参数. | ✅ |
| text_io.py | Core | Linux X11 文本输入 — `X11TextInput.enter`：纯 ASCII 经 stdin 交给 `xdotool type --delay N --file -`（分块，不进命令行参数，不碰剪贴板）；含任何非 ASCII 字符的文本整段走 xclip + Ctrl+V 粘贴（xdotool 逐字符重映射键码，真实应用会丢字、串字），粘贴前读原剪贴板（3 秒超时防所有者卡死），`finally` 写回原内容（原为空也写回空串，凭据不残留），实例级锁串行重叠粘贴；ASCII 分块失败报「typed N of M characters」；命令运行器由后端注入. | ✅ |
| probes.py | Core | Linux 屏幕与环境只读探测 — `probe_linux_capturable`（scrot / gnome-screenshot 实截一张并判定可用）、`detect_linux_resolution`（xdpyinfo / xrandr，读不到回退 1920x1080）、`read_screen_context`（xdotool 读活动窗口标题与鼠标位置，读不到回退空串 / (0, 0)）、`linux_permission_status`（xdotool、截图工具、DISPLAY / Wayland 是否齐备）；仅被 `backend.py` 引用. | ✅ |
