//! Linux WebKitGTK + NVIDIA GPU 兼容性修复。

#[cfg(target_os = "linux")]
pub fn apply_linux_gpu_workarounds() {
    use std::env;
    use std::path::Path;

    if env::var("MYRM_FORCE_GPU_ACCEL").as_deref() == Ok("1") {
        return;
    }
    if env::var("WEBKIT_DISABLE_DMABUF_RENDERER").is_ok() {
        return;
    }

    let is_nvidia = Path::new("/proc/driver/nvidia/version").exists();
    let is_wayland = env::var("WAYLAND_DISPLAY").is_ok()
        || env::var("XDG_SESSION_TYPE").as_deref() == Ok("wayland");

    if is_nvidia && is_wayland {
        env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
        env::set_var("__NV_DISABLE_EXPLICIT_SYNC", "1");
        eprintln!(
            "⚠️ NVIDIA + Wayland detected — applied GPU compatibility workaround \
             (WEBKIT_DISABLE_DMABUF_RENDERER=1). Override with MYRM_FORCE_GPU_ACCEL=1"
        );
    } else if is_nvidia {
        env::set_var("__NV_DISABLE_EXPLICIT_SYNC", "1");
        eprintln!("ℹ️ NVIDIA GPU detected — applied __NV_DISABLE_EXPLICIT_SYNC=1");
    }
}

#[cfg(not(target_os = "linux"))]
pub fn apply_linux_gpu_workarounds() {}
